import { getToken, setToken } from "./auth";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export class AuthError extends Error {}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleUnauthorized(res: Response): Promise<never> {
  if (res.status === 401) {
    setToken(null);
    throw new AuthError("Session expired, please sign in again");
  }
  throw new Error(`Request failed (${res.status}): ${await res.text()}`);
}

export type Color = "white" | "black";
export type GameMode = "ai" | "pvp";

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
  last_move_uci: string | null;
  game_id: string;
  mode: GameMode;
  opponent_name: string | null;
}

export interface MoveResponse {
  ok: boolean;
  san: string | null;
  uci: string | null;
  error: string | null;
  state: GameState;
}

export interface MyGame {
  game_id: string;
  mode: GameMode;
  your_color: Color;
  opponent_name: string | null;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    return handleUnauthorized(res);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    return handleUnauthorized(res);
  }
  return res.json() as Promise<T>;
}

export async function newAiGame(humanColor: Color): Promise<GameState> {
  return post<GameState>("/games/ai", { human_color: humanColor });
}

export async function getGameState(gameId: string): Promise<GameState> {
  return get<GameState>(`/games/${gameId}`);
}

export async function getMyGames(): Promise<MyGame[]> {
  return get<MyGame[]>("/my/games");
}

export interface MatchmakingResult {
  matched: boolean;
  game_id: string | null;
}

export async function joinMatchmaking(): Promise<MatchmakingResult> {
  return post<MatchmakingResult>("/matchmaking/join");
}

export async function leaveMatchmaking(): Promise<void> {
  await post("/matchmaking/leave");
}

export async function playMove(gameId: string, uci: string): Promise<MoveResponse> {
  return post<MoveResponse>(`/games/${gameId}/move`, { uci });
}

export async function playAiMove(gameId: string): Promise<MoveResponse> {
  return post<MoveResponse>(`/games/${gameId}/ai_move`);
}

export async function askAboutPosition(gameId: string, question: string): Promise<string> {
  const data = await post<{ answer: string }>(`/games/${gameId}/ask`, { question });
  return data.answer;
}

export async function explainLastMove(gameId: string): Promise<string> {
  const data = await post<{ comment: string }>(`/games/${gameId}/explain_last_move`);
  return data.comment;
}

export interface TacticInfo {
  tactic_available: boolean;
  side: Color;
  eval_gain_cp: number;
}

export async function getTactic(gameId: string): Promise<TacticInfo> {
  return get<TacticInfo>(`/games/${gameId}/tactic`);
}

export async function explainTactic(gameId: string): Promise<string> {
  const data = await post<{ explanation: string }>(`/games/${gameId}/explain_tactic`);
  return data.explanation;
}

function wsBase(): string {
  if (API_BASE.startsWith("http://") || API_BASE.startsWith("https://")) {
    return API_BASE.replace(/^http/, "ws");
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${API_BASE}`;
}

export function connectGameSocket(gameId: string): WebSocket {
  const token = getToken() ?? "";
  return new WebSocket(`${wsBase()}/ws/games/${gameId}?token=${encodeURIComponent(token)}`);
}

export function connectLobbySocket(): WebSocket {
  const token = getToken() ?? "";
  return new WebSocket(`${wsBase()}/ws/lobby?token=${encodeURIComponent(token)}`);
}
