"""
FastAPI wrapper exposing the chess game over HTTP for the frontend/ UI.

Run with:
    uvicorn server:app --reload --port 8000

Defaults to the local Ollama backend (see llm.py) so the server runs without
an ANTHROPIC_API_KEY. Requires `ollama serve` running and the model pulled:
    ollama pull qwen2.5-coder:3b
Override with LLM_BACKEND=anthropic to use Claude instead.

Games are persisted in SQLite (db.py) and cached live in games.py, keyed by
game_id - each authenticated user can have several games in flight (one vs
the AI, one or more PvP), unlike the old single-global-board version of
this server.
"""

import os

os.environ.setdefault("LLM_BACKEND", "ollama")

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import games
import realtime
from analysis_agent import analysis_agent
from auth import GoogleUser, consume_ws_ticket, create_ws_ticket, get_current_user
from db import init_db
from engine import detect_tactic
from move_agent import explain_move, explain_tactic_move

app = FastAPI(title="Chess Agents API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://192.168.0.100:5173",
        "http://192.168.0.100:5174",
        "https://chessagents123.com",
        "https://www.chessagents123.com",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


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


class MatchmakingResponse(BaseModel):
    matched: bool
    game_id: str | None = None


class WsTicketResponse(BaseModel):
    ticket: str


@app.get("/me")
def me(user: GoogleUser = Depends(get_current_user)) -> dict:
    return user.to_dict()


@app.post("/ws-ticket", response_model=WsTicketResponse)
def ws_ticket(user: GoogleUser = Depends(get_current_user)) -> WsTicketResponse:
    return WsTicketResponse(ticket=create_ws_ticket(user))


@app.post("/games/ai")
def new_ai_game(req: NewGameRequest, user: GoogleUser = Depends(get_current_user)) -> dict:
    if req.human_color not in ("white", "black"):
        raise HTTPException(400, "human_color must be 'white' or 'black'")
    row = games.create_ai_game(user, req.human_color)
    return games.get_state(row.id, user)


@app.post("/matchmaking/join", response_model=MatchmakingResponse)
async def matchmaking_join(user: GoogleUser = Depends(get_current_user)) -> MatchmakingResponse:
    opponent_id = realtime.join_queue(user.sub)
    if opponent_id is None:
        return MatchmakingResponse(matched=False)

    white_id, black_id = games.random_color_pair(user.sub, opponent_id)
    row = games.create_pvp_game(white_id, black_id)
    await realtime.notify_matched(opponent_id, row.id)
    return MatchmakingResponse(matched=True, game_id=row.id)


@app.post("/matchmaking/leave")
def matchmaking_leave(user: GoogleUser = Depends(get_current_user)) -> dict:
    realtime.leave_queue(user.sub)
    return {"ok": True}


@app.get("/my/games")
def my_games(user: GoogleUser = Depends(get_current_user)) -> list[dict]:
    return games.list_my_games(user.sub)


@app.get("/games/{game_id}")
def game_state(game_id: str, user: GoogleUser = Depends(get_current_user)) -> dict:
    return games.get_state(game_id, user)


@app.post("/games/{game_id}/move", response_model=MoveResponse)
async def move(
    game_id: str, req: MoveRequest, user: GoogleUser = Depends(get_current_user)
) -> MoveResponse:
    result, state = games.make_move(game_id, user, req.uci)
    if result.ok and state["mode"] == "pvp":
        states = games.states_by_participant(game_id)
        await realtime.broadcast_game_state(game_id, states)
    return MoveResponse(ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=state)


@app.post("/games/{game_id}/ai_move", response_model=MoveResponse)
async def ai_move(game_id: str, user: GoogleUser = Depends(get_current_user)) -> MoveResponse:
    result, state = await run_in_threadpool(games.make_ai_move, game_id, user)
    return MoveResponse(ok=result.ok, san=result.san, uci=result.uci, error=result.error, state=state)


@app.post("/games/{game_id}/explain_last_move", response_model=ExplainResponse)
def explain_last_move(game_id: str, user: GoogleUser = Depends(get_current_user)) -> ExplainResponse:
    _, last_ai_move = games.get_ai_game_and_last_move(game_id, user)
    if last_ai_move is None:
        raise HTTPException(400, "No AI move has been played yet")
    comment = explain_move(
        fen_before=last_ai_move["fen_before"],
        san=last_ai_move["san"],
        move_history_san=last_ai_move["move_history_san"],
        color=last_ai_move["color"],
    )
    return ExplainResponse(comment=comment)


@app.get("/games/{game_id}/tactic", response_model=TacticResponse)
def tactic(game_id: str, user: GoogleUser = Depends(get_current_user)) -> TacticResponse:
    game, _ = games.get_ai_game_and_last_move(game_id, user)
    side = "white" if game.board.turn else "black"
    board_snapshot = game.board.copy(stack=False)
    result = detect_tactic(board_snapshot)
    return TacticResponse(
        tactic_available=result["tactic"], side=side, eval_gain_cp=result["eval_gain_cp"]
    )


@app.post("/games/{game_id}/explain_tactic", response_model=TacticExplainResponse)
def explain_tactic(game_id: str, user: GoogleUser = Depends(get_current_user)) -> TacticExplainResponse:
    game, _ = games.get_ai_game_and_last_move(game_id, user)
    side = "white" if game.board.turn else "black"
    board_snapshot = game.board.copy()
    result = detect_tactic(board_snapshot)
    if not result["tactic"] or result["move"] is None:
        raise HTTPException(400, "No tactic available in the current position")
    san = board_snapshot.san(result["move"])
    explanation = explain_tactic_move(
        fen=board_snapshot.fen(), san=san, side=side, eval_gain_cp=result["eval_gain_cp"]
    )
    return TacticExplainResponse(explanation=explanation)


@app.post("/games/{game_id}/ask", response_model=AskResponse)
def ask(game_id: str, req: AskRequest, user: GoogleUser = Depends(get_current_user)) -> AskResponse:
    game, _ = games.get_ai_game_and_last_move(game_id, user)
    board_snapshot = game.board.copy()
    history = game.move_history_san()
    answer = analysis_agent(board_snapshot, history, req.question)
    return AskResponse(answer=answer)


@app.websocket("/ws/games/{game_id}")
async def ws_game(websocket: WebSocket, game_id: str) -> None:
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=4401)
        return
    try:
        user = await run_in_threadpool(consume_ws_ticket, ticket)
        state = await run_in_threadpool(games.get_state, game_id, user)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    realtime.register_game_socket(game_id, user.sub, websocket)
    await websocket.send_json({"type": "state", "state": state})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        realtime.unregister_game_socket(game_id, websocket)


@app.websocket("/ws/lobby")
async def ws_lobby(websocket: WebSocket) -> None:
    ticket = websocket.query_params.get("ticket")
    if not ticket:
        await websocket.close(code=4401)
        return
    try:
        user = await run_in_threadpool(consume_ws_ticket, ticket)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    realtime.register_lobby_socket(user.sub, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        realtime.unregister_lobby_socket(user.sub)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
