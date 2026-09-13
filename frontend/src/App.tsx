import { useEffect, useState } from "react";
import Game from "./Game";
import Lobby from "./Lobby";
import Login from "./Login";
import { decodeUser, getToken, setToken, subscribeToken, type AuthUser } from "./auth";
import type { GameState } from "./api";
import "./App.css";

function App() {
  const [token, setTokenState] = useState<string | null>(getToken());
  const [activeGame, setActiveGame] = useState<GameState | null>(null);

  useEffect(() => subscribeToken(setTokenState), []);
  useEffect(() => {
    if (!token) setActiveGame(null);
  }, [token]);

  const user: AuthUser | null = token ? decodeUser(token) : null;

  function handleSignOut() {
    window.google?.accounts.id.disableAutoSelect();
    setToken(null);
  }

  if (!token) {
    return <Login />;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-row">
          <div>
            <h1>Chess Agents</h1>
            <p>Play against a local LLM, or find another player, and ask questions about the position any time.</p>
          </div>
          {user && (
            <div className="user-badge">
              {user.picture && <img src={user.picture} alt="" className="user-avatar" />}
              <span className="user-name">{user.name ?? user.email}</span>
              <button type="button" className="sign-out-button" onClick={handleSignOut}>
                Sign out
              </button>
            </div>
          )}
        </div>
      </header>

      {activeGame ? (
        <Game initialState={activeGame} onExit={() => setActiveGame(null)} />
      ) : (
        <Lobby onEnterGame={setActiveGame} />
      )}
    </div>
  );
}

export default App;
