"""
Analysis agent: answers a natural-language question about the current
position. Read-only — it never proposes or applies a move (that's
move_agent's job via the orchestrator). Computed facts (material, check,
ASCII board) are handed to the model alongside the FEN, since small local
models reason about a rendered board far better than about FEN alone.
"""

import chess

from llm import call_llm

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

SYSTEM_PROMPT = """You are a helpful chess coach answering questions about an
in-progress game. You are given the position (FEN, an ASCII diagram, material
count, and move history) and a question from the player.

Rules:
- Answer only using the position given. Be concise (2-4 sentences unless the
  question asks for a deeper explanation).
- If asked for the best move, name it in SAN and briefly justify it.
- Do not invent pieces or moves that aren't consistent with the position.
"""


def _material(board: chess.Board) -> str:
    white = sum(
        PIECE_VALUES.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == chess.WHITE
    )
    black = sum(
        PIECE_VALUES.get(p.piece_type, 0)
        for p in board.piece_map().values()
        if p.color == chess.BLACK
    )
    diff = white - black
    if diff == 0:
        return f"White {white}, Black {black} (even)"
    leader = "White" if diff > 0 else "Black"
    return f"White {white}, Black {black} ({leader} +{abs(diff)})"


def analysis_agent(board: chess.Board, move_history_san: list[str], question: str) -> str:
    turn = "White" if board.turn else "Black"
    history = " ".join(move_history_san) if move_history_san else "(game start)"
    legal_san = ", ".join(board.san(m) for m in board.legal_moves)

    user = f"""Position (FEN): {board.fen()}

Board:
{board}

Turn to move: {turn}
In check: {board.is_check()}
Material: {_material(board)}
Move history (SAN): {history}
Legal moves for {turn}: {legal_san}

Question: {question}
"""
    return call_llm(SYSTEM_PROMPT, user, max_tokens=400)
