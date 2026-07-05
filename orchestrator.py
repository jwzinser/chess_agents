"""
Orchestrator: picks and applies the AI's move for the side to move.

Move *selection* is done by the local search engine (engine.py) — it's
always legal by construction, so unlike the sql_agents orchestrator there's
no retry loop here. Explaining the move in plain language is a separate,
optional step (see move_agent.explain_move), kept out of this hot path so
the board updates immediately without waiting on an LLM call.
"""

import os

from chess_engine import ChessGame, MoveResult
from engine import find_best_move

TIME_LIMIT = float(os.environ.get("ENGINE_TIME_LIMIT", "2.0"))
MAX_DEPTH = int(os.environ.get("ENGINE_MAX_DEPTH", "5"))


def ai_move_orchestrator(game: ChessGame) -> MoveResult:
    move, score = find_best_move(game.board, time_limit=TIME_LIMIT, max_depth=MAX_DEPTH)
    uci = move.uci()
    print(f"[Orchestrator] Engine chose {game.board.san(move)} (score {score})")
    return game.push_uci(uci)
