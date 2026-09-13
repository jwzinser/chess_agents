"""
Game service layer: owns the live in-memory ChessGame boards and mediates
every read/write against the `games`/`moves` tables in db.py.

One cache entry per game_id, hydrated lazily from the persisted FEN on
first touch (so a server restart doesn't lose in-progress games) and kept
in sync on every move. A per-game lock serializes move application so two
requests for the same game can't race each other.
"""

import random
import threading
from dataclasses import dataclass

import chess
from fastapi import HTTPException
from sqlalchemy import select

from auth import GoogleUser
from chess_engine import ChessGame, MoveResult
from db import AI_USER_ID, Game, Move, SessionLocal, User
from orchestrator import ai_move_orchestrator


@dataclass
class _CacheEntry:
    game: ChessGame
    lock: threading.Lock
    last_ai_move: dict | None = None


_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()


def _hydrate(row: Game, session) -> ChessGame:
    """Rebuild a ChessGame for a game not yet in the in-memory cache (first
    touch after a server restart, or first touch ever this process).

    Replays the persisted moves from scratch rather than doing
    `chess.Board(row.fen)`, because a board built straight from a FEN has an
    empty move_stack - ChessGame.move_history_san() (and last_move_uci)
    replay/read that stack and would otherwise only ever see moves made
    after this hydration, crashing or misreporting history for any game
    that had moves before the restart.
    """
    game = ChessGame()
    if row.mode == "ai":
        game.human_color = chess.WHITE if row.black_user_id == AI_USER_ID else chess.BLACK

    moves = session.scalars(select(Move).where(Move.game_id == row.id).order_by(Move.ply)).all()
    board = chess.Board()
    for m in moves:
        board.push_uci(m.uci)
    game.board = board
    return game


def _entry(row: Game, session) -> _CacheEntry:
    with _CACHE_LOCK:
        entry = _CACHE.get(row.id)
        if entry is None:
            entry = _CacheEntry(game=_hydrate(row, session), lock=threading.Lock())
            _CACHE[row.id] = entry
        return entry


def _result_for(status: str, board: chess.Board) -> str | None:
    if status == "checkmate":
        return "1-0" if board.turn == chess.BLACK else "0-1"
    if status == "stalemate" or status.startswith("draw"):
        return "1/2-1/2"
    return None


def _persist_move(session, row: Game, game: ChessGame, mover_color: str, result: MoveResult) -> None:
    state = game.to_state()
    row.fen = game.board.fen()
    row.status = state["status"]
    row.result = _result_for(state["status"], game.board)
    session.add(row)
    session.add(
        Move(
            game_id=row.id,
            ply=len(game.board.move_stack),
            uci=result.uci,
            san=result.san,
            color=mover_color,
        )
    )
    session.commit()


def require_participant(row: Game, user_id: str) -> str:
    if row.white_user_id == user_id:
        return "white"
    if row.black_user_id == user_id:
        return "black"
    raise HTTPException(403, "You are not a participant in this game")


def create_ai_game(user: GoogleUser, human_color: str) -> Game:
    if human_color not in ("white", "black"):
        raise HTTPException(400, "human_color must be 'white' or 'black'")
    with SessionLocal() as session:
        row = Game(
            mode="ai",
            white_user_id=user.sub if human_color == "white" else AI_USER_ID,
            black_user_id=AI_USER_ID if human_color == "white" else user.sub,
            fen=chess.Board().fen(),
        )
        session.add(row)
        session.commit()
        return row


def create_pvp_game(white_id: str, black_id: str) -> Game:
    with SessionLocal() as session:
        row = Game(mode="pvp", white_user_id=white_id, black_user_id=black_id, fen=chess.Board().fen())
        session.add(row)
        session.commit()
        return row


def get_row(session, game_id: str) -> Game:
    row = session.get(Game, game_id)
    if row is None:
        raise HTTPException(404, "Game not found")
    return row


def state_for(row: Game, game: ChessGame, viewer_id: str, session) -> dict:
    state = game.to_state()
    your_color = "white" if row.white_user_id == viewer_id else "black"
    opponent_id = row.black_user_id if your_color == "white" else row.white_user_id
    opponent = session.get(User, opponent_id)
    state["human_color"] = your_color
    state["game_id"] = row.id
    state["mode"] = row.mode
    state["opponent_name"] = (opponent.name or opponent.email) if opponent else None
    return state


def get_state(game_id: str, user: GoogleUser) -> dict:
    with SessionLocal() as session:
        row = get_row(session, game_id)
        require_participant(row, user.sub)
        game = _entry(row, session).game
        return state_for(row, game, user.sub, session)


def states_by_participant(game_id: str) -> dict[str, dict]:
    """Per-viewer states for both sides of a game, keyed by user_id.

    `state_for` bakes in the viewer's own color/opponent name, so a single
    state dict can't just be broadcast to both sockets in a PvP game - each
    side needs their own.
    """
    with SessionLocal() as session:
        row = get_row(session, game_id)
        game = _entry(row, session).game
        return {
            row.white_user_id: state_for(row, game, row.white_user_id, session),
            row.black_user_id: state_for(row, game, row.black_user_id, session),
        }


def make_move(game_id: str, user: GoogleUser, uci: str) -> tuple[MoveResult, dict]:
    with SessionLocal() as session:
        row = get_row(session, game_id)
        color = require_participant(row, user.sub)
        entry = _entry(row, session)
        with entry.lock:
            game = entry.game
            if game.board.is_game_over():
                raise HTTPException(400, "Game is already over")
            side_to_move = "white" if game.board.turn == chess.WHITE else "black"
            if side_to_move != color:
                raise HTTPException(400, "It is not your turn")

            result = game.push_uci(uci)
            if result.ok:
                _persist_move(session, row, game, color, result)
            return result, state_for(row, game, user.sub, session)


def make_ai_move(game_id: str, user: GoogleUser) -> tuple[MoveResult, dict]:
    with SessionLocal() as session:
        row = get_row(session, game_id)
        require_participant(row, user.sub)
        if row.mode != "ai":
            raise HTTPException(400, "This game has no AI opponent")
        entry = _entry(row, session)
        with entry.lock:
            game = entry.game
            if game.board.is_game_over():
                raise HTTPException(400, "Game is already over")
            if game.turn_is_human():
                raise HTTPException(400, "It is the human player's turn")

            color = "white" if game.board.turn == chess.WHITE else "black"
            fen_before = game.board.fen()
            history_before = game.move_history_san()

            result = ai_move_orchestrator(game)
            if result.ok:
                _persist_move(session, row, game, color, result)
                entry.last_ai_move = {
                    "fen_before": fen_before,
                    "san": result.san,
                    "color": color,
                    "move_history_san": history_before + [result.san],
                }
            return result, state_for(row, game, user.sub, session)


def get_ai_game_and_last_move(game_id: str, user: GoogleUser) -> tuple[ChessGame, dict | None]:
    with SessionLocal() as session:
        row = get_row(session, game_id)
        require_participant(row, user.sub)
        if row.mode != "ai":
            raise HTTPException(400, "This is not an AI game")
        entry = _entry(row, session)
        return entry.game, entry.last_ai_move


def list_my_games(user_id: str) -> list[dict]:
    with SessionLocal() as session:
        from sqlalchemy import or_, select

        rows = session.scalars(
            select(Game)
            .where(
                or_(Game.white_user_id == user_id, Game.black_user_id == user_id),
                Game.status.in_(["in_progress", "check"]),
            )
            .order_by(Game.updated_at.desc())
        ).all()
        return [
            {
                "game_id": row.id,
                "mode": row.mode,
                "your_color": "white" if row.white_user_id == user_id else "black",
                "opponent_name": (
                    session.get(User, row.black_user_id if row.white_user_id == user_id else row.white_user_id)
                    or User(name=None)
                ).name,
            }
            for row in rows
        ]


def random_color_pair(a: str, b: str) -> tuple[str, str]:
    pair = [a, b]
    random.shuffle(pair)
    return pair[0], pair[1]
