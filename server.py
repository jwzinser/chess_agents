"""
FastAPI wrapper exposing the chess game over HTTP for the frontend/ UI.

Run with:
    uvicorn server:app --reload --port 8000

Defaults to the local Ollama backend (see llm.py) so the server runs without
an ANTHROPIC_API_KEY. Requires `ollama serve` running and the model pulled:
    ollama pull qwen2.5-coder:3b
Override with LLM_BACKEND=anthropic to use Claude instead.
"""

import os
import threading
import time
import uuid

os.environ.setdefault("LLM_BACKEND", "ollama")

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analysis_agent import analysis_agent
from chess_engine import ChessGame
from engine import detect_tactic
from move_agent import explain_move, explain_tactic_move
from orchestrator import ai_move_orchestrator

app = FastAPI(title="Chess Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://192.168.0.100:5173",
        "http://192.168.0.100:5174",
        "http://67.205.142.155",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class GameSession:
    """One player's game: its own board, lock, and last-AI-move record.

    Concurrent players each get their own instance instead of sharing the
    single global game the server used to keep, so their moves can no
    longer clobber each other.
    """

    def __init__(self, human_color: str = "white"):
        self.game = ChessGame(human_color=human_color)
        self.lock = threading.Lock()
        self.last_ai_move: dict | None = None
        self.last_access = time.time()


# Sessions are in-memory only (no DB), same minimalism as the old single
# global game - they just don't stomp on each other anymore. Idle sessions
# are swept on access so a long-running server doesn't accumulate abandoned
# games forever.
SESSIONS: dict[str, GameSession] = {}
SESSIONS_LOCK = threading.Lock()
SESSION_TTL_SECONDS = 6 * 60 * 60


def _sweep_expired_sessions() -> None:
    cutoff = time.time() - SESSION_TTL_SECONDS
    with SESSIONS_LOCK:
        expired = [gid for gid, s in SESSIONS.items() if s.last_access < cutoff]
        for gid in expired:
            del SESSIONS[gid]


def get_session(game_id: str | None) -> GameSession:
    _sweep_expired_sessions()
    if not game_id:
        raise HTTPException(400, "Missing X-Game-Id header; call /new_game first")
    with SESSIONS_LOCK:
        session = SESSIONS.get(game_id)
    if session is None:
        raise HTTPException(404, "Unknown or expired game_id; call /new_game to start a new one")
    session.last_access = time.time()
    return session


GameId = Header(default=None, alias="X-Game-Id")


class NewGameRequest(BaseModel):
    human_color: str = "white"


class MoveRequest(BaseModel):
    uci: str


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


class ExplainResponse(BaseModel):
    comment: str


class TacticResponse(BaseModel):
    tactic_available: bool
    side: str
    eval_gain_cp: int


class TacticExplainResponse(BaseModel):
    explanation: str


class MoveResponse(BaseModel):
    ok: bool
    san: str | None = None
    uci: str | None = None
    error: str | None = None
    state: dict


@app.post("/new_game")
def new_game(req: NewGameRequest) -> dict:
    if req.human_color not in ("white", "black"):
        raise HTTPException(400, "human_color must be 'white' or 'black'")
    game_id = uuid.uuid4().hex
    session = GameSession(human_color=req.human_color)
    with SESSIONS_LOCK:
        SESSIONS[game_id] = session
    state = session.game.to_state()
    state["game_id"] = game_id
    return state


@app.get("/state")
def state(x_game_id: str | None = GameId) -> dict:
    session = get_session(x_game_id)
    with session.lock:
        return session.game.to_state()


@app.post("/move", response_model=MoveResponse)
def move(req: MoveRequest, x_game_id: str | None = GameId) -> MoveResponse:
    session = get_session(x_game_id)
    with session.lock:
        game = session.game
        if game.board.is_game_over():
            raise HTTPException(400, "Game is already over")
        if not game.turn_is_human():
            raise HTTPException(400, "It is not the human player's turn")

        result = game.push_uci(req.uci)
        return MoveResponse(
            ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=game.to_state()
        )


@app.post("/ai_move", response_model=MoveResponse)
def ai_move(x_game_id: str | None = GameId) -> MoveResponse:
    session = get_session(x_game_id)
    with session.lock:
        game = session.game
        if game.board.is_game_over():
            raise HTTPException(400, "Game is already over")
        if game.turn_is_human():
            raise HTTPException(400, "It is the human player's turn")

        color = "white" if game.board.turn else "black"
        fen_before = game.board.fen()
        history_before = game.move_history_san()

        result = ai_move_orchestrator(game)
        if result.ok:
            session.last_ai_move = {
                "fen_before": fen_before,
                "san": result.san,
                "color": color,
                "move_history_san": history_before + [result.san],
            }
        return MoveResponse(
            ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=game.to_state()
        )


@app.post("/explain_last_move", response_model=ExplainResponse)
def explain_last_move(x_game_id: str | None = GameId) -> ExplainResponse:
    session = get_session(x_game_id)
    if session.last_ai_move is None:
        raise HTTPException(400, "No AI move has been played yet")
    comment = explain_move(
        fen_before=session.last_ai_move["fen_before"],
        san=session.last_ai_move["san"],
        move_history_san=session.last_ai_move["move_history_san"],
        color=session.last_ai_move["color"],
    )
    return ExplainResponse(comment=comment)


@app.get("/tactic", response_model=TacticResponse)
def tactic(x_game_id: str | None = GameId) -> TacticResponse:
    session = get_session(x_game_id)
    # Snapshot under the lock, then search the snapshot: the search itself
    # takes up to half a second and must not hold up concurrent moves.
    with session.lock:
        side = "white" if session.game.board.turn else "black"
        board_snapshot = session.game.board.copy(stack=False)
    result = detect_tactic(board_snapshot)
    return TacticResponse(
        tactic_available=result["tactic"], side=side, eval_gain_cp=result["eval_gain_cp"]
    )


@app.post("/explain_tactic", response_model=TacticExplainResponse)
def explain_tactic(x_game_id: str | None = GameId) -> TacticExplainResponse:
    session = get_session(x_game_id)
    with session.lock:
        side = "white" if session.game.board.turn else "black"
        board_snapshot = session.game.board.copy()
    result = detect_tactic(board_snapshot)
    if not result["tactic"] or result["move"] is None:
        raise HTTPException(400, "No tactic available in the current position")
    san = board_snapshot.san(result["move"])
    explanation = explain_tactic_move(
        fen=board_snapshot.fen(), san=san, side=side, eval_gain_cp=result["eval_gain_cp"]
    )
    return TacticExplainResponse(explanation=explanation)


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, x_game_id: str | None = GameId) -> AskResponse:
    session = get_session(x_game_id)
    with session.lock:
        board_snapshot = session.game.board.copy()
        history = session.game.move_history_san()
    answer = analysis_agent(board_snapshot, history, req.question)
    return AskResponse(answer=answer)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
