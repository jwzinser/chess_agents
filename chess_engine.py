"""
Chess engine wrapper: owns the single in-memory game, validates and applies
moves, and reports position state. Plays the role of the "executor" from the
sql_agents demo — it's the source of truth the LLM agents are checked
against, never the LLM itself.
"""

from dataclasses import dataclass
from typing import Optional

import chess
import chess.pgn


def _status(board: chess.Board) -> str:
    if board.is_checkmate():
        return "checkmate"
    if board.is_stalemate():
        return "stalemate"
    if board.is_insufficient_material():
        return "draw (insufficient material)"
    if board.is_seventyfive_moves():
        return "draw (75-move rule)"
    if board.is_fivefold_repetition():
        return "draw (fivefold repetition)"
    if board.is_check():
        return "check"
    return "in_progress"


@dataclass
class MoveResult:
    ok: bool
    san: Optional[str] = None
    uci: Optional[str] = None
    error: Optional[str] = None


class ChessGame:
    def __init__(self, human_color: str = "white"):
        self.board = chess.Board()
        self.human_color = chess.WHITE if human_color == "white" else chess.BLACK

    def reset(self, human_color: str = "white") -> None:
        self.board = chess.Board()
        self.human_color = chess.WHITE if human_color == "white" else chess.BLACK

    @property
    def ai_color(self) -> bool:
        return not self.human_color

    def turn_is_human(self) -> bool:
        return self.board.turn == self.human_color

    def legal_moves(self) -> list[dict]:
        return [
            {"uci": m.uci(), "san": self.board.san(m)}
            for m in self.board.legal_moves
        ]

    def push_uci(self, uci: str) -> MoveResult:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return MoveResult(ok=False, error=f"'{uci}' is not a well-formed UCI move")
        if move not in self.board.legal_moves:
            return MoveResult(ok=False, error=f"'{uci}' is not a legal move in this position")
        san = self.board.san(move)
        self.board.push(move)
        return MoveResult(ok=True, san=san, uci=move.uci())

    def push_san(self, san: str) -> MoveResult:
        try:
            move = self.board.parse_san(san)
        except ValueError as e:
            return MoveResult(ok=False, error=str(e))
        uci = move.uci()
        self.board.push(move)
        return MoveResult(ok=True, san=san, uci=uci)

    def move_history_san(self) -> list[str]:
        history = []
        board = chess.Board()
        for move in self.board.move_stack:
            history.append(board.san(move))
            board.push(move)
        return history

    def to_state(self) -> dict:
        return {
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn else "black",
            "human_color": "white" if self.human_color else "black",
            "legal_moves": self.legal_moves(),
            "move_history_san": self.move_history_san(),
            "status": _status(self.board),
            "game_over": self.board.is_game_over(),
            "in_check": self.board.is_check(),
        }
