const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const GAME_ID_STORAGE_KEY = "chess_game_id";

function getGameId(): string | null {
  try {
    return localStorage.getItem(GAME_ID_STORAGE_KEY);
  } catch {
    return null;
  }
}

function setGameId(id: string): void {
  try {
    localStorage.setItem(GAME_ID_STORAGE_KEY, id);
  } catch {
    // Private browsing / storage disabled: the session just won't persist
    // across reloads, which is a fine degradation for a demo app.
  }
}

function gameIdHeaders(): Record<string, string> {
  const id = getGameId();
  return id ? { "X-Game-Id": id } : {};
}

export type Color = "white" | "black";

export interface LegalMove {
  uci: string;
  san: string;
}

export interface GameState {
  fen: string;
  turn: Color;
  human_color: Color;
  legal_moves: LegalMove[];
  move_history_san: string[];
  status: string;
  game_over: boolean;
  in_check: boolean;
  attacked_squares: string[];
}

export interface MoveResponse {
  ok: boolean;
  san: string | null;
  uci: string | null;
  error: string | null;
  state: GameState;
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...gameIdHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}): ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function newGame(humanColor: Color): Promise<GameState> {
  const state = await request<GameState & { game_id: string }>("/new_game", {
    human_color: humanColor,
  });
  setGameId(state.game_id);
  return state;
}

export async function getState(): Promise<GameState> {
  const res = await fetch(`${API_BASE}/state`, { headers: gameIdHeaders() });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}): ${await res.text()}`);
  }
  return res.json() as Promise<GameState>;
}

export async function playMove(uci: string): Promise<MoveResponse> {
  return request<MoveResponse>("/move", { uci });
}

export async function playAiMove(): Promise<MoveResponse> {
  return request<MoveResponse>("/ai_move");
}

export async function askAboutPosition(question: string): Promise<string> {
  const data = await request<{ answer: string }>("/ask", { question });
  return data.answer;
}

export async function explainLastMove(): Promise<string> {
  const data = await request<{ comment: string }>("/explain_last_move");
  return data.comment;
}

export interface TacticInfo {
  tactic_available: boolean;
  side: Color;
  eval_gain_cp: number;
}

export async function getTactic(): Promise<TacticInfo> {
  const res = await fetch(`${API_BASE}/tactic`, { headers: gameIdHeaders() });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}): ${await res.text()}`);
  }
  return res.json() as Promise<TacticInfo>;
}

export async function explainTactic(): Promise<string> {
  const data = await request<{ explanation: string }>("/explain_tactic");
  return data.explanation;
}
