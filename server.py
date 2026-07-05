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

os.environ.setdefault("LLM_BACKEND", "ollama")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from analysis_agent import analysis_agent
from chess_engine import ChessGame
from orchestrator import ai_move_orchestrator

app = FastAPI(title="Chess Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

GAME = ChessGame()


class NewGameRequest(BaseModel):
    human_color: str = "white"


class MoveRequest(BaseModel):
    uci: str


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


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
    GAME.reset(human_color=req.human_color)
    return GAME.to_state()


@app.get("/state")
def state() -> dict:
    return GAME.to_state()


@app.post("/move", response_model=MoveResponse)
def move(req: MoveRequest) -> MoveResponse:
    if GAME.board.is_game_over():
        raise HTTPException(400, "Game is already over")
    if not GAME.turn_is_human():
        raise HTTPException(400, "It is not the human player's turn")

    result = GAME.push_uci(req.uci)
    return MoveResponse(
        ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=GAME.to_state()
    )


@app.post("/ai_move", response_model=MoveResponse)
def ai_move() -> MoveResponse:
    if GAME.board.is_game_over():
        raise HTTPException(400, "Game is already over")
    if GAME.turn_is_human():
        raise HTTPException(400, "It is the human player's turn")

    result = ai_move_orchestrator(GAME)
    return MoveResponse(
        ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=GAME.to_state()
    )


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    answer = analysis_agent(GAME.board, GAME.move_history_san(), req.question)
    return AskResponse(answer=answer)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
