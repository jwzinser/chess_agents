"""
A small self-contained chess engine: material + piece-square-table
evaluation, negamax search with alpha-beta pruning, capture-ordering, a
quiescence search on captures, and iterative deepening under a time budget.

This is what actually picks the AI's moves now — local LLMs are simply too
weak at board-tracking to play sane chess, even when constrained to a legal
move list. The LLM's role shifts to narrating the engine's choice in
plain language (see move_agent.explain_move), not choosing it.
"""

import time

import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# Piece-square tables, White's perspective, row 0 = rank 8 down to row 7 =
# rank 1 (i.e. as conventionally published). Mirrored vertically for Black.
PAWN_PST = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [50, 50, 50, 50, 50, 50, 50, 50],
    [10, 10, 20, 30, 30, 20, 10, 10],
    [5, 5, 10, 25, 25, 10, 5, 5],
    [0, 0, 0, 20, 20, 0, 0, 0],
    [5, -5, -10, 0, 0, -10, -5, 5],
    [5, 10, 10, -20, -20, 10, 10, 5],
    [0, 0, 0, 0, 0, 0, 0, 0],
]

KNIGHT_PST = [
    [-50, -40, -30, -30, -30, -30, -40, -50],
    [-40, -20, 0, 0, 0, 0, -20, -40],
    [-30, 0, 10, 15, 15, 10, 0, -30],
    [-30, 5, 15, 20, 20, 15, 5, -30],
    [-30, 0, 15, 20, 20, 15, 0, -30],
    [-30, 5, 10, 15, 15, 10, 5, -30],
    [-40, -20, 0, 5, 5, 0, -20, -40],
    [-50, -40, -30, -30, -30, -30, -40, -50],
]

BISHOP_PST = [
    [-20, -10, -10, -10, -10, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 10, 10, 5, 0, -10],
    [-10, 5, 5, 10, 10, 5, 5, -10],
    [-10, 0, 10, 10, 10, 10, 0, -10],
    [-10, 10, 10, 10, 10, 10, 10, -10],
    [-10, 5, 0, 0, 0, 0, 5, -10],
    [-20, -10, -10, -10, -10, -10, -10, -20],
]

ROOK_PST = [
    [0, 0, 0, 0, 0, 0, 0, 0],
    [5, 10, 10, 10, 10, 10, 10, 5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [-5, 0, 0, 0, 0, 0, 0, -5],
    [0, 0, 0, 5, 5, 0, 0, 0],
]

QUEEN_PST = [
    [-20, -10, -10, -5, -5, -10, -10, -20],
    [-10, 0, 0, 0, 0, 0, 0, -10],
    [-10, 0, 5, 5, 5, 5, 0, -10],
    [-5, 0, 5, 5, 5, 5, 0, -5],
    [0, 0, 5, 5, 5, 5, 0, -5],
    [-10, 5, 5, 5, 5, 5, 0, -10],
    [-10, 0, 5, 0, 0, 0, 0, -10],
    [-20, -10, -10, -5, -5, -10, -10, -20],
]

KING_PST_MID = [
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-30, -40, -40, -50, -50, -40, -40, -30],
    [-20, -30, -30, -40, -40, -30, -30, -20],
    [-10, -20, -20, -20, -20, -20, -20, -10],
    [20, 20, 0, 0, 0, 0, 20, 20],
    [20, 30, 10, 0, 0, 10, 30, 20],
]

KING_PST_END = [
    [-50, -40, -30, -20, -20, -30, -40, -50],
    [-30, -20, -10, 0, 0, -10, -20, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 30, 40, 40, 30, -10, -30],
    [-30, -10, 20, 30, 30, 20, -10, -30],
    [-30, -30, 0, 0, 0, 0, -30, -30],
    [-50, -30, -30, -30, -30, -30, -30, -50],
]

PST = {
    chess.PAWN: PAWN_PST,
    chess.KNIGHT: KNIGHT_PST,
    chess.BISHOP: BISHOP_PST,
    chess.ROOK: ROOK_PST,
    chess.QUEEN: QUEEN_PST,
}

ENDGAME_MATERIAL_THRESHOLD = 1600  # combined non-pawn, non-king centipawns


class SearchTimeout(Exception):
    pass


def _is_endgame(board: chess.Board) -> bool:
    total = 0
    for piece_type in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        total += len(board.pieces(piece_type, chess.WHITE)) * PIECE_VALUES[piece_type]
        total += len(board.pieces(piece_type, chess.BLACK)) * PIECE_VALUES[piece_type]
    return total <= ENDGAME_MATERIAL_THRESHOLD


def _pst_value(piece_type: chess.PieceType, color: chess.Color, square: chess.Square, endgame: bool) -> int:
    table = KING_PST_END if (piece_type == chess.KING and endgame) else (
        KING_PST_MID if piece_type == chess.KING else PST[piece_type]
    )
    file = chess.square_file(square)
    rank = chess.square_rank(square)  # 0-indexed, 0 = rank 1
    row = 7 - rank if color == chess.WHITE else rank
    return table[row][file]


def evaluate(board: chess.Board) -> int:
    """Score in centipawns from the perspective of the side to move."""
    if board.is_checkmate():
        return -999_000
    if board.is_stalemate() or board.is_insufficient_material():
        return 0

    endgame = _is_endgame(board)
    score = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type] + _pst_value(piece.piece_type, piece.color, square, endgame)
        score += value if piece.color == chess.WHITE else -value
    return score if board.turn == chess.WHITE else -score


def _capture_score(board: chess.Board, move: chess.Move) -> int:
    if not board.is_capture(move):
        return 0
    victim = board.piece_type_at(move.to_square)
    victim_value = PIECE_VALUES[victim] if victim else PIECE_VALUES[chess.PAWN]  # en passant
    attacker = board.piece_type_at(move.from_square)
    attacker_value = PIECE_VALUES[attacker] if attacker else 0
    return victim_value * 10 - attacker_value


def _ordered_moves(board: chess.Board) -> list[chess.Move]:
    return sorted(board.legal_moves, key=lambda m: _capture_score(board, m), reverse=True)


def _quiescence(board: chess.Board, alpha: int, beta: int, deadline: float) -> int:
    if time.monotonic() > deadline:
        raise SearchTimeout
    stand_pat = evaluate(board)
    if stand_pat >= beta:
        return beta
    alpha = max(alpha, stand_pat)

    captures = [m for m in board.legal_moves if board.is_capture(m)]
    captures.sort(key=lambda m: _capture_score(board, m), reverse=True)
    for move in captures:
        board.push(move)
        try:
            score = -_quiescence(board, -beta, -alpha, deadline)
        finally:
            board.pop()
        if score >= beta:
            return beta
        alpha = max(alpha, score)
    return alpha


def _negamax(
    board: chess.Board, depth: int, alpha: int, beta: int, deadline: float
) -> tuple[int, chess.Move | None]:
    if time.monotonic() > deadline:
        raise SearchTimeout
    if board.is_game_over():
        return evaluate(board), None
    if depth == 0:
        return _quiescence(board, alpha, beta, deadline), None

    best_score = -float("inf")
    best_move = None
    for move in _ordered_moves(board):
        board.push(move)
        try:
            score, _ = _negamax(board, depth - 1, -beta, -alpha, deadline)
        finally:
            board.pop()
        score = -score

        if score > best_score:
            best_score = score
            best_move = move
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best_score, best_move


def find_best_move(
    board: chess.Board, time_limit: float = 2.0, max_depth: int = 5
) -> tuple[chess.Move, int]:
    """Iterative deepening negamax search, bounded by `time_limit` seconds."""
    deadline = time.monotonic() + time_limit
    best_move = next(iter(board.legal_moves))
    best_score = 0

    depth = 1
    while depth <= max_depth:
        try:
            score, move = _negamax(board, depth, -float("inf"), float("inf"), deadline)
        except SearchTimeout:
            break
        if move is not None:
            best_move, best_score = move, score
        depth += 1

    return best_move, best_score


if __name__ == "__main__":
    b = chess.Board()
    mv, sc = find_best_move(b, time_limit=2.0)
    print(b.san(mv), sc)
