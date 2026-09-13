"""
In-memory websocket registry and matchmaking queue.

All ephemeral by design: a per-game set of connected sockets (for live
move push), a per-user lobby socket + waiting queue (to notify a queued
player once they're paired), and nothing here survives a restart. Games
themselves are persisted in db.py - losing this state just means a queued
player has to click "Find opponent" again, or a viewer misses a live push
and has to re-fetch state.

Single uvicorn process (no --workers), so a plain dict + lock is enough -
no pub/sub broker needed.
"""

import threading

from fastapi import WebSocket

_game_sockets: dict[str, dict[WebSocket, str]] = {}
_lobby_sockets: dict[str, WebSocket] = {}
_queue: list[str] = []
_lock = threading.Lock()


def register_game_socket(game_id: str, user_id: str, ws: WebSocket) -> None:
    with _lock:
        _game_sockets.setdefault(game_id, {})[ws] = user_id


def unregister_game_socket(game_id: str, ws: WebSocket) -> None:
    with _lock:
        sockets = _game_sockets.get(game_id)
        if sockets is not None:
            sockets.pop(ws, None)
            if not sockets:
                _game_sockets.pop(game_id, None)


async def broadcast_game_state(game_id: str, states_by_user: dict[str, dict]) -> None:
    """states_by_user maps user_id -> that user's own-perspective state dict,
    since each viewer needs their own human_color/opponent_name (see
    games.states_by_participant)."""
    with _lock:
        sockets = list(_game_sockets.get(game_id, {}).items())
    for ws, user_id in sockets:
        state = states_by_user.get(user_id)
        if state is None:
            continue
        try:
            await ws.send_json({"type": "state", "state": state})
        except Exception:
            pass


def register_lobby_socket(user_id: str, ws: WebSocket) -> None:
    with _lock:
        _lobby_sockets[user_id] = ws


def unregister_lobby_socket(user_id: str) -> None:
    with _lock:
        _lobby_sockets.pop(user_id, None)
        if user_id in _queue:
            _queue.remove(user_id)


def join_queue(user_id: str) -> str | None:
    """Pair with a waiting user if one exists, else join the queue.

    Returns the opponent's user_id if this join completes a match (in
    which case the caller does NOT get queued), or None if the caller is
    now the one waiting.
    """
    with _lock:
        if user_id in _queue:
            return None
        while _queue:
            opponent = _queue.pop(0)
            if opponent != user_id:
                return opponent
        _queue.append(user_id)
        return None


def leave_queue(user_id: str) -> None:
    with _lock:
        if user_id in _queue:
            _queue.remove(user_id)


async def notify_matched(user_id: str, game_id: str) -> None:
    with _lock:
        ws = _lobby_sockets.get(user_id)
    if ws is not None:
        try:
            await ws.send_json({"type": "matched", "game_id": game_id})
        except Exception:
            pass
