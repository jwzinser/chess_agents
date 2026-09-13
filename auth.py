"""
Google Sign-In verification for the Chess Agents API.

The frontend obtains an ID token from Google Identity Services and sends it
as `Authorization: Bearer <id_token>`. We verify it against Google's public
keys and the configured GOOGLE_CLIENT_ID (audience) on every protected
request. There is no session/user store - a valid, unexpired Google ID
token is all that's required, matching the "login gate" scope of this app.
"""

import os
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
