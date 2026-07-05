# Chess Agents (frontend)

A React + TypeScript UI: a click-to-move chessboard plus a Q&A panel that
asks the `chess_agents` backend (`../server.py`) questions about the
current position over HTTP.

```
click piece, click square ──▶ POST /move ──▶ board updates
(AI's turn) ──▶ POST /ai_move (auto) ──▶ board updates
"is my king safe?" ──▶ POST /ask ──▶ answer in chat panel
```

## Run the backend

From `chess_agents/` (one level up):

```bash
uv venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/uvicorn server:app --reload --port 8000
```

Defaults to a local Ollama model — see `../README.md` for setup.

## Run the frontend

```bash
npm install
npm run dev
```

Open the printed URL (default `http://localhost:5173`). The app calls the
backend at `http://localhost:8000` by default — override with a
`VITE_API_BASE` env var (see `.env.example`).

## Notes

- `src/api.ts` — thin fetch wrapper around `/new_game`, `/state`, `/move`,
  `/ai_move`, `/ask`.
- `src/Board.tsx` — renders the board from a FEN string and handles
  click-to-move; legal destination squares are computed from the
  `legal_moves` list the backend returns (no chess rules client-side).
- `src/App.tsx` — game state, new-game controls, auto-triggers `/ai_move`
  when it becomes the AI's turn, and the Q&A chat panel.
- Pawn promotions always auto-pick queen client-side.
- CORS on the backend (`../server.py`) is restricted to
  `http://localhost:5173`; update `allow_origins` there if you serve the
  frontend from elsewhere.
