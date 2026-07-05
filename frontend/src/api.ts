const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

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
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}): ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function newGame(humanColor: Color): Promise<GameState> {
  return request<GameState>("/new_game", { human_color: humanColor });
}

export async function getState(): Promise<GameState> {
  const res = await fetch(`${API_BASE}/state`);
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
