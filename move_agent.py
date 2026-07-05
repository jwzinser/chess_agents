"""
Move agent: given the current position, picks a move for the side to play.
Does not validate or apply anything itself — the orchestrator checks its
choice against the engine's legal move list and retries on a miss.
"""

import re
from dataclasses import dataclass
from typing import Optional

from llm import call_llm

SYSTEM_PROMPT = """You are a strong chess engine choosing a move to play.

You will be given the current position as a FEN string, the move history in
SAN, and the full list of legal moves in SAN notation. Pick the single best
legal move.

Rules:
- Reply with ONLY the move exactly as it is spelled in the legal moves list
  (same SAN string, including check '+' or mate '#' suffix if present).
- No explanation, no move number, no markdown, no extra words.
"""


@dataclass
class MoveDraft:
    san: str


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```\s*|```$", "", text, flags=re.MULTILINE).strip()
    # Model sometimes prefixes with a move number like "12. Nf3" or "12...Nf3".
    text = re.sub(r"^\d+\.+\s*", "", text)
    return text.split()[0] if text.split() else text


def move_agent(
    fen: str,
    legal_san: list[str],
    move_history_san: list[str],
    color: str,
    feedback: Optional[str] = None,
) -> MoveDraft:
    history = " ".join(move_history_san) if move_history_san else "(game start)"
    user = (
        f"You are playing: {color}\n"
        f"FEN: {fen}\n"
        f"Move history (SAN): {history}\n"
        f"Legal moves (SAN): {', '.join(legal_san)}\n\n"
        "Which move do you play?"
    )
    if feedback:
        user += f"\n\n{feedback}"
    raw = call_llm(SYSTEM_PROMPT, user, max_tokens=32)
    return MoveDraft(san=_clean(raw))
