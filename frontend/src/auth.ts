const STORAGE_KEY = "chess_agents_google_id_token";

export interface AuthUser {
  sub: string;
  email?: string;
  name?: string;
  picture?: string;
}

type AuthListener = (token: string | null) => void;

let currentToken: string | null = localStorage.getItem(STORAGE_KEY);
const listeners = new Set<AuthListener>();

export function getToken(): string | null {
  return currentToken;
}

export function setToken(token: string | null): void {
  currentToken = token;
  if (token) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
  listeners.forEach((listener) => listener(token));
}

export function subscribeToken(listener: AuthListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// The ID token is a JWT; decode the payload for display purposes only.
// The backend independently verifies the token's signature on every request.
export function decodeUser(token: string): AuthUser | null {
  try {
    const payload = token.split(".")[1];
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const data = JSON.parse(decodeURIComponent(escape(json)));
    return { sub: data.sub, email: data.email, name: data.name, picture: data.picture };
  } catch {
    return null;
  }
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
          disableAutoSelect: () => void;
          prompt: () => void;
        };
      };
    };
  }
}
