# Chess Agents

A multiplayer chess app where move selection is done by a real search
engine rather than an LLM: local LLMs are just too weak at board-tracking
to play sane chess, even when constrained to a list of legal moves. So a
small **search engine** (material + piece-square evaluation, alpha-beta,
quiescence search) picks the AI's moves, an **orchestrator** applies them,
a **move commentary agent** narrates the choice in plain language after
the fact, and a separate **analysis agent** answers freeform questions
about the position — the LLM's role is language, not legality or
strength. On top of that sits Google Sign-In auth, a SQLite-backed game
store, and websocket-based realtime sync so two people can actually play
each other.

## Architecture

```
                              ┌─────────────────────────┐
  browser  ── HTTPS ──▶ nginx │ chessagents123.com       │
                              │  /            → SPA      │
                              │  /api/*       → uvicorn   │──▶ 127.0.0.1:8000
                              └─────────────────────────┘        (FastAPI, systemd)
```

Requests reach FastAPI only through nginx: uvicorn binds to
`127.0.0.1:8000` and is never exposed to the internet directly, and nginx
terminates TLS (Let's Encrypt via certbot) and reverse-proxies `/api/`
to it. The frontend is a static Vite build served straight from disk.

### Move flow (AI game)

```
human plays a move ──▶ POST /games/{id}/move ──▶ python-chess validates + applies, persisted to SQLite
                                              │
                                     (if AI's turn) POST /games/{id}/ai_move
                                              │
                              orchestrator asks engine.find_best_move()
                             (negamax + alpha-beta + quiescence, ~2s budget)
                                              │
                                     applied (always legal), state persisted + returned
                                              │
                          (async, non-blocking) POST /games/{id}/explain_last_move
                              move_agent narrates why in one sentence

"what's happening here?" ──▶ POST /games/{id}/ask ──▶ analysis_agent ──▶ answer
                                (FEN + ASCII board + material handed to LLM)
```

### Move flow (PvP game)

Matchmaking pairs two waiting users (`realtime.join_queue`); a `pvp` row
is created with a random color assignment and both players are pushed
onto the same game. Each move a player makes is validated and persisted
exactly like an AI game, then broadcast over that game's open websockets
so the opponent's board updates live without polling.

### Persistence and process model

- Single small VM, single uvicorn process (no `--workers`): `db.py` uses
  a plain synchronous SQLAlchemy engine against a local SQLite file — no
  async driver or migration framework needed at this size.
- `games.py` keeps one live `ChessGame` per `game_id` in an in-memory
  cache, hydrated lazily from persisted moves on first touch (so a server
  restart doesn't lose in-progress games), with a per-game lock so two
  requests for the same game can't race each other.
- `realtime.py`'s websocket registry and matchmaking queue are pure
  in-memory state and intentionally don't survive a restart — the games
  themselves are safe in SQLite, so losing this just means a queued
  player clicks "Find opponent" again, or a viewer misses one live push
  and re-fetches state.

## Security design

**Authentication.** The frontend uses Google Identity Services to obtain
a Google ID token (a signed JWT) and sends it as `Authorization: Bearer
<token>` on every REST call. `auth.py` verifies the token's signature and
audience (`GOOGLE_CLIENT_ID`) against Google's public keys on every
protected request — there's no separate session store or server-side
login state; a valid, unexpired Google ID token *is* the session, and
`FastAPI`'s `Depends(get_current_user)` gates every route that touches
game data.

**Websocket auth without leaking the token.** Browsers can't send custom
headers on a WebSocket handshake, so the long-lived Google ID token can't
be attached directly to a `/ws/*` connection without putting it in the
URL — and therefore into nginx/uvicorn access logs — as a plaintext query
string. Instead, a client that already holds a verified token exchanges
it for a short-lived (30s), single-use ticket via `POST /ws-ticket`
(`auth.create_ws_ticket`); only that random ticket goes in the socket
URL, so even if it ends up in a log line, it's already useless by the
time anyone reads it, and it can only ever be redeemed once
(`auth.consume_ws_ticket`).

**Authorization.** Verifying *who* a caller is isn't enough — `games.py`
separately checks that the caller is actually a participant in the game
they're touching (`require_participant`), so an authenticated user can
still only read or move in their own games, not anyone else's.

**Transport.** Production traffic is HTTPS-only: nginx holds a Let's
Encrypt certificate for `chessagents123.com`, and plain HTTP requests are
301-redirected to HTTPS (or 404 for any other host, including the bare
droplet IP). The `CORSMiddleware` allow-list in `server.py` is scoped to
the real domain plus known local-dev origins — no wildcard origins.

**Network exposure.** `ufw` only opens 22 (SSH), 80, and 443. Uvicorn
itself listens on loopback only, so the backend is reachable exclusively
through nginx's reverse proxy, never directly from the internet.

## Files

- `chess_engine.py` — owns a single `ChessGame` (`python-chess`);
  validates and applies moves, reports FEN/turn/status. The source of
  truth the AI's move is checked against.
- `engine.py` — the actual chess engine: material + piece-square-table
  evaluation, negamax search with alpha-beta pruning and capture ordering,
  a quiescence search on captures, iterative deepening under a time budget.
  No LLM involved — this is what makes the AI play competently.
- `orchestrator.py` — asks `engine.py` for the best move and applies it via
  `chess_engine.py`. No retry loop needed since the engine's moves are
  always legal by construction.
- `move_agent.py` — LLM call that narrates a move the engine already
  played, in one sentence. Never chooses or validates a move.
- `analysis_agent.py` — LLM call that answers a question about the current
  position (read-only, never proposes a move to play)
- `llm.py` — shared LLM client helper (Anthropic or local Ollama backend)
- `auth.py` — Google ID token verification and the short-lived websocket
  ticket exchange (see Security design above)
- `db.py` — SQLAlchemy models (`User`, `Game`, `Move`) and SQLite engine
- `games.py` — service layer: in-memory `ChessGame` cache backed by the
  DB, participant authorization, move application, matchmaking pairing
- `realtime.py` — in-memory websocket registry and matchmaking queue for
  live game/lobby push
- `server.py` — FastAPI app: auth, game, matchmaking and websocket routes
- `frontend/` — React + TypeScript: login, lobby/matchmaking, chessboard
  + Q&A chat panel (see `frontend/README.md`)

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

You'll also need a Google OAuth client ID for Sign-In:

```bash
# .env (backend)
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com

# frontend/.env
VITE_API_BASE=http://localhost:8000
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
```

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

Open the URL printed by Vite (default `http://localhost:5173`), sign in
with Google, then either start a game against the AI or click "Find
opponent" to be matched with another signed-in player. In an AI game,
pick a color and click "New Game" — click a piece then a highlighted
square to move; the AI replies automatically when it's its turn (search
takes up to `ENGINE_TIME_LIMIT` seconds, default 2), and a one-line
explanation of its move shows up in the chat panel shortly after. Ask
questions about the position (e.g. "what's my best move?", "is my king
safe?", "who's better here and why?") in the same panel any time.

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

- Promotions always auto-promote to queen (frontend appends `q` to the UCI
  string on a promoting pawn move) — no underpromotion support, kept simple.
- The engine is intentionally lightweight (no opening book, no transposition
  table, no null-move pruning) — it plays solid, blunder-avoiding chess at a
  club level, not master strength. It's meant to be a believable opponent,
  not the strongest possible one.
- `/games/{id}/ai_move` never calls an LLM, so it's fast and deterministic
  given a time budget; `/games/{id}/explain_last_move` is a separate,
  optional call the frontend fires after the board updates so commentary
  never blocks play.
- `analysis_agent` is handed a rendered ASCII board and computed material
  count alongside the FEN, since small local models reason far better about
  a diagram than about FEN alone.
