"""
Move commentary agent: given a move the engine already chose and applied,
produces a short plain-language rationale for it. Never chooses or
validates a move itself — engine.py does that; this is pure narration,
called after the board has already updated so it never blocks gameplay.
"""

from llm import call_llm

SYSTEM_PROMPT = """You are a chess commentator. You are given a position
before a move, the move that was just played (in SAN), and the move
history. Explain in ONE short sentence why the move makes sense (e.g. what
it develops, defends, attacks, or wins).

Rules:
- One sentence, no more than ~25 words.
- No markdown, no move number prefix, just the sentence.
"""


def explain_move(fen_before: str, san: str, move_history_san: list[str], color: str) -> str:
    history = " ".join(move_history_san[:-1]) if len(move_history_san) > 1 else "(game start)"
    user = (
        f"Position before the move (FEN): {fen_before}\n"
        f"Move history so far: {history}\n"
        f"{color} just played: {san}\n\n"
        "Why does this move make sense?"
    )
    return call_llm(SYSTEM_PROMPT, user, max_tokens=80).strip()


TACTIC_SYSTEM_PROMPT = """You are a chess coach pointing out a tactic the
side to move has available in the current position (not yet played).

Rules:
- 2-3 short sentences.
- Name the move in SAN and say what kind of tactic it is (fork, pin, skewer,
  discovered attack, hanging piece, or forced mate), and why it works.
- No markdown.
"""


def explain_tactic_move(fen: str, san: str, side: str, eval_gain_cp: int) -> str:
    pawns = eval_gain_cp / 100
    user = (
        f"Position (FEN): {fen}\n"
        f"Side to move: {side}\n"
        f"The tactical move available: {san}\n"
        f"It gains roughly {pawns:.1f} pawns of material/advantage over any quiet move.\n\n"
        "Explain the tactic."
    )
    return call_llm(TACTIC_SYSTEM_PROMPT, user, max_tokens=150).strip()
