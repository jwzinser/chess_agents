import { useEffect, useRef, useState } from "react";
import {
  connectLobbySocket,
  getGameState,
  getMyGames,
  joinMatchmaking,
  leaveMatchmaking,
  newAiGame,
  type Color,
  type GameState,
  type MyGame,
} from "./api";

interface Props {
  onEnterGame: (state: GameState) => void;
}

type Mode = "idle" | "ai-picker" | "searching";

function Lobby({ onEnterGame }: Props) {
  const [myGames, setMyGames] = useState<MyGame[] | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [humanColorChoice, setHumanColorChoice] = useState<Color>("white");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lobbySocketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    getMyGames()
      .then(setMyGames)
      .catch(() => setMyGames([]));
  }, []);

  useEffect(() => {
    return () => {
      lobbySocketRef.current?.close();
    };
  }, []);

  async function resume(gameId: string) {
    setBusy(true);
    setError(null);
    try {
      onEnterGame(await getGameState(gameId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resume game");
    } finally {
      setBusy(false);
    }
  }

  async function startAiGame() {
    setBusy(true);
    setError(null);
    try {
      onEnterGame(await newAiGame(humanColorChoice));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start game");
      setBusy(false);
    }
  }

  async function findOpponent() {
    setError(null);
    setMode("searching");
    const socket = connectLobbySocket();
    lobbySocketRef.current = socket;
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "matched") {
        socket.close();
        getGameState(data.game_id)
          .then(onEnterGame)
          .catch((err) => {
            setError(err instanceof Error ? err.message : "Could not load matched game");
            setMode("idle");
          });
      }
    };

    try {
      const result = await joinMatchmaking();
      if (result.matched && result.game_id) {
        socket.close();
        onEnterGame(await getGameState(result.game_id));
      }
    } catch (err) {
      socket.close();
      setError(err instanceof Error ? err.message : "Matchmaking failed");
      setMode("idle");
    }
  }

  async function cancelSearch() {
    lobbySocketRef.current?.close();
    lobbySocketRef.current = null;
    setMode("idle");
    try {
      await leaveMatchmaking();
    } catch {
      /* best-effort */
    }
  }

  if (mode === "searching") {
    return (
      <div className="lobby">
        <p className="lobby-status">Searching for an opponent…</p>
        <button type="button" onClick={cancelSearch}>
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="lobby">
      {error && <div className="move-error">{error}</div>}

      {myGames === null && <p className="lobby-status">Loading your games…</p>}

      {myGames !== null && myGames.length > 0 && (
        <div className="lobby-section">
          <h2>Resume a game</h2>
          <ul className="lobby-game-list">
            {myGames.map((g) => (
              <li key={g.game_id}>
                <button type="button" disabled={busy} onClick={() => resume(g.game_id)}>
                  {g.mode === "ai" ? "vs AI" : `vs ${g.opponent_name ?? "opponent"}`} — playing{" "}
                  {g.your_color}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="lobby-section">
        <h2>New game</h2>
        <div className="lobby-actions">
          {mode !== "ai-picker" ? (
            <button type="button" disabled={busy} onClick={() => setMode("ai-picker")}>
              Play vs AI
            </button>
          ) : (
            <div className="game-controls">
              <label>
                Play as
                <select
                  value={humanColorChoice}
                  onChange={(e) => setHumanColorChoice(e.target.value as Color)}
                >
                  <option value="white">White</option>
                  <option value="black">Black</option>
                </select>
              </label>
              <button type="button" disabled={busy} onClick={startAiGame}>
                Start
              </button>
            </div>
          )}
          <button type="button" disabled={busy} onClick={findOpponent}>
            Find opponent
          </button>
        </div>
      </div>
    </div>
  );
}

export default Lobby;
