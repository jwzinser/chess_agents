"""
Orchestrator: asks the move agent for the AI's next move, retrying with the
error fed back to the agent if it names an illegal or unrecognized move
(mirrors the analytics/executor retry loop in sql_agents). Falls back to a
random legal move if the agent still can't land on one, so the game always
progresses even with a small local model.
"""

import random

from chess_engine import ChessGame, MoveResult
from move_agent import move_agent

MAX_ATTEMPTS = 3


def ai_move_orchestrator(game: ChessGame) -> MoveResult:
    color = "white" if game.board.turn else "black"
    feedback = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        legal_san = [m["san"] for m in game.legal_moves()]
        draft = move_agent(
            fen=game.board.fen(),
            legal_san=legal_san,
            move_history_san=game.move_history_san(),
            color=color,
            feedback=feedback,
        )
        print(f"[Orchestrator] Attempt {attempt} — move agent chose: {draft.san}")

        result = game.push_san(draft.san)
        if result.ok:
            print(f"[Orchestrator] Move accepted: {result.san}")
            return result

        print(f"[Orchestrator] Rejected: {result.error}")
        feedback = (
            f"'{draft.san}' is not one of the legal moves. "
            f"Choose exactly one string from this list: {', '.join(legal_san)}"
        )

    legal = game.legal_moves()
    fallback = random.choice(legal)
    print(f"[Orchestrator] Giving up on the agent, playing random legal move: {fallback['san']}")
    return game.push_san(fallback["san"])
