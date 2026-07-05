# Chess Agents Demo

A minimal chess app in the same shape as `../sql_agents`: a **move agent**
picks the AI's move, an **orchestrator** validates it against the real
engine (retrying on an illegal choice), and a separate **analysis agent**
answers freeform questions about the position — all backed by a local LLM
by default.

```
human plays a move ──▶ POST /move ──▶ python-chess validates + applies
                                              │
                                     (if AI's turn) POST /ai_move
                                              │
                                     move_agent drafts a SAN move
                                              │
                              orchestrator checks it against legal moves
                                  │ illegal (feedback loop, up to 3 tries) │
                                  └──────────────◀────────────────────────┘
                                              │ legal
                                     applied, board state returned

"what's happening here?" ──▶ POST /ask ──▶ analysis_agent ──▶ answer
                                (FEN + ASCII board + material handed to LLM)
```

## Files

- `chess_engine.py` — owns the single in-memory game (`python-chess`);
  validates and applies moves, reports FEN/turn/status. The source of
  truth the agents are checked against.
- `move_agent.py` — LLM call that picks a move (SAN) from the position
- `orchestrator.py` — validates the move agent's pick against legal moves,
  retrying with feedback up to 3 times, falling back to a random legal move
  if the model still can't land on one
- `analysis_agent.py` — LLM call that answers a question about the current
  position (read-only, never proposes a move to play)
- `llm.py` — shared LLM client helper (Anthropic or local Ollama backend)
- `server.py` — FastAPI wrapper: `/new_game`, `/state`, `/move`, `/ai_move`, `/ask`
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

`server.py` defaults to the local Ollama backend (`LLM_BACKEND=ollama`), so
it runs without an `ANTHROPIC_API_KEY` — just make sure `ollama serve` is
running and a model is pulled:

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
move; the AI replies automatically when it's its turn. Ask questions about
the position (e.g. "what's my best move?", "is my king safe?", "who's
better here and why?") in the panel underneath the board.

Set `LLM_BACKEND=anthropic` before starting the backend to use Claude
(`claude-haiku-4-5`) for both agents instead:

```bash
export LLM_BACKEND=anthropic
.venv/bin/uvicorn server:app --reload --port 8000
```

## Notes

- Game state is a single in-memory game per server process (no DB, no
  multi-session support) — restarting the server or calling `/new_game`
  resets it, same minimalism as `shop.db` in sql_agents.
- Promotions always auto-promote to queen (frontend appends `q` to the UCI
  string on a promoting pawn move) — no underpromotion support, kept simple.
- A 3B local model will play weak, sometimes-illegal-looking chess; the
  orchestrator's legal-move retry + random fallback exists specifically to
  paper over that so a game always finishes rather than getting stuck.
- `analysis_agent` is handed a rendered ASCII board and computed material
  count alongside the FEN, since small local models reason far better about
  a diagram than about FEN alone.
# chess_agents
