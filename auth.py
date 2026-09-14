"""
Google Sign-In verification for the Chess Agents API.

The frontend obtains an ID token from Google Identity Services and sends it
as `Authorization: Bearer <id_token>`. We verify it against Google's public
keys and the configured GOOGLE_CLIENT_ID (audience) on every protected
request. There is no session/user store - a valid, unexpired Google ID
token is all that's required, matching the "login gate" scope of this app.

Browsers can't send custom headers on a WebSocket handshake, so the long-
lived Google ID token can't be used directly to authenticate `/ws/*`
connections without it ending up in the URL - and therefore in nginx/uvicorn
access logs - as plaintext query string. Instead, a client that already has
a verified token exchanges it (via POST /ws-ticket) for a random, single-use
ticket that's only valid for a few seconds; that's what goes in the socket
URL, so a log line is worthless to anyone reading it after the fact.
"""

import os
import secrets
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from db import SessionLocal, upsert_user

load_dotenv(Path(__file__).parent / ".env")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")

_google_request = google_requests.Request()


class GoogleUser:
    def __init__(self, payload: dict):
        self.sub: str = payload["sub"]
        self.email: str | None = payload.get("email")
        self.name: str | None = payload.get("name")
        self.picture: str | None = payload.get("picture")

    def to_dict(self) -> dict:
        return {"sub": self.sub, "email": self.email, "name": self.name, "picture": self.picture}


def verify_token(token: str) -> GoogleUser:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(500, "Server is missing GOOGLE_CLIENT_ID configuration")

    try:
        payload = google_id_token.verify_oauth2_token(token, _google_request, GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise HTTPException(401, f"Invalid Google ID token: {exc}") from None

    user = GoogleUser(payload)
    with SessionLocal() as session:
        upsert_user(session, user.sub, user.email, user.name, user.picture)
    return user


def get_current_user(authorization: str | None = Header(None)) -> GoogleUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    return verify_token(authorization.removeprefix("Bearer ").strip())


_WS_TICKET_TTL_SECONDS = 30

_ws_tickets: dict[str, tuple[GoogleUser, float]] = {}
_ws_tickets_lock = threading.Lock()


def create_ws_ticket(user: GoogleUser) -> str:
    """Mint a random, single-use ticket for `user`, valid for a few seconds."""
    ticket = secrets.token_urlsafe(32)
    with _ws_tickets_lock:
        _ws_tickets[ticket] = (user, time.monotonic() + _WS_TICKET_TTL_SECONDS)
    return ticket


def consume_ws_ticket(ticket: str) -> GoogleUser:
    """Redeem a ticket for the user it was issued to. Each ticket works once."""
    with _ws_tickets_lock:
        entry = _ws_tickets.pop(ticket, None)
    if entry is None:
        raise HTTPException(401, "Invalid or expired ticket")
    user, expires_at = entry
    if time.monotonic() > expires_at:
        raise HTTPException(401, "Invalid or expired ticket")
    return user
