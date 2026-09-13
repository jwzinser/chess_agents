# Chess Agents Demo

A chess app in the same shape as `../sql_agents`, but with the move
selection done by a real search engine rather than an LLM: local LLMs are
just too weak at board-tracking to play sane chess, even when constrained
to a list of legal moves. So a small **search engine** (material +
piece-square evaluation, alpha-beta, quiescence search) picks the AI's
moves, an **orchestrator** applies them, a **move commentary agent**
narrates the choice in plain language after the fact, and a separate
**analysis agent** answers freeform questions about the position — the
LLM's role is language, not legality or strength.

```
human plays a move ──▶ POST /move ──▶ python-chess validates + applies
                                              │
                                     (if AI's turn) POST /ai_move
                                              │
                              orchestrator asks engine.find_best_move()
                             (negamax + alpha-beta + quiescence, ~2s budget)
                                              │
                                     applied (always legal), board returned
                                              │
                          (async, non-blocking) POST /explain_last_move
                              move_agent narrates why in one sentence

"what's happening here?" ──▶ POST /ask ──▶ analysis_agent ──▶ answer
                                (FEN + ASCII board + material handed to LLM)
```

## Files

- `chess_engine.py` — owns the single in-memory game (`python-chess`);
  validates and applies moves, reports FEN/turn/status. The source of
  truth the AI's move is checked against.
- `engine.py` — the actual chess engine: material + piece-square-table
  evaluation, negamax search with alpha-beta pruning and capture ordering,
  a quiescence search on captures, iterative deepening under a time budget.
  No LLM involved — this is what makes the AI play competently.
- `orchestrator.py` — asks `engine.py` for the best move and applies it via
  `chess_engine.py`. No retry loop needed (unlike sql_agents) since the
  engine's moves are always legal by construction.
- `move_agent.py` — LLM call that narrates a move the engine already
  played, in one sentence. Never chooses or validates a move.
- `analysis_agent.py` — LLM call that answers a question about the current
  position (read-only, never proposes a move to play)
- `llm.py` — shared LLM client helper (Anthropic or local Ollama backend)
- `server.py` — FastAPI wrapper: `/new_game`, `/state`, `/move`, `/ai_move`,
  `/explain_last_move`, `/ask`
- `frontend/` — React + TypeScript chessboard + Q&A chat panel (see `frontend/README.md`)

## Setup

```bash
cd chess_agents
uv venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Always invoke the venv's own `python`/`uvicorn` explicitly
(`.venv/bin/python`, `.venv/bin/uvicorn`) rather than relying on `source
.venv/bin/activate` — your shell may auto-activate a different venv on
startup.

## Run the app

`server.py` defaults to the local Ollama backend (`LLM_BACKEND=ollama`) for
move commentary and Q&A, so it runs without an `ANTHROPIC_API_KEY` — just
make sure `ollama serve` is running and a model is pulled:

```bash
brew install ollama       # if not already installed
ollama serve               # separate terminal
ollama pull qwen2.5-coder:3b
```

Then:

```bash
# terminal 1: backend
.venv/bin/uvicorn server:app --reload --port 8000

# terminal 2: frontend
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (default `http://localhost:5173`). Pick a
color and click "New Game" — click a piece then a highlighted square to
move; the AI replies automatically when it's its turn (search takes up to
`ENGINE_TIME_LIMIT` seconds, default 2), and a one-line explanation of its
move shows up in the chat panel shortly after. Ask questions about the
position (e.g. "what's my best move?", "is my king safe?", "who's better
here and why?") in the same panel any time.

Set `LLM_BACKEND=anthropic` before starting the backend to use Claude
(`claude-haiku-4-5`) for commentary/Q&A instead:

```bash
export LLM_BACKEND=anthropic
.venv/bin/uvicorn server:app --reload --port 8000
```

Tune engine strength/speed with env vars:

```bash
export ENGINE_TIME_LIMIT=4.0   # seconds per AI move, default 2.0
export ENGINE_MAX_DEPTH=6      # ply cap, default 5
```

## Notes

- Game state is a single in-memory game per server process (no DB, no
  multi-session support) — restarting the server or calling `/new_game`
  resets it, same minimalism as `shop.db` in sql_agents.
- Promotions always auto-promote to queen (frontend appends `q` to the UCI
  string on a promoting pawn move) — no underpromotion support, kept simple.
- The engine is intentionally lightweight (no opening book, no transposition
  table, no null-move pruning) — it plays solid, blunder-avoiding chess at a
  club level, not master strength. It's meant to be a believable opponent,
  not the strongest possible one.
- `/ai_move` no longer calls an LLM at all, so it's fast and deterministic
  given a time budget; `/explain_last_move` is a separate, optional call the
  frontend fires after the board updates so commentary never blocks play.
- `analysis_agent` is handed a rendered ASCII board and computed material
  count alongside the FEN, since small local models reason far better about
  a diagram than about FEN alone.
# chess_agents
