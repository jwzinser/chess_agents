import { useEffect, useRef, useState } from "react";
import Board from "./Board";
import {
  askAboutPosition,
  explainLastMove,
  getState,
  newGame,
  playAiMove,
  playMove,
  type Color,
  type GameState,
} from "./api";
import "./App.css";

type Role = "user" | "assistant" | "error";

interface ChatMessage {
  id: number;
  role: Role;
  content: string;
}

let nextId = 0;

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatPgn(moves: string[]): string {
  const parts: string[] = [];
  for (let i = 0; i < moves.length; i += 2) {
    const moveNo = i / 2 + 1;
    const white = moves[i];
    const black = moves[i + 1];
    parts.push(black ? `${moveNo}. ${white} ${black}` : `${moveNo}. ${white}`);
  }
  return parts.join("  ");
}

function statusLabel(state: GameState): string {
  if (state.game_over) {
    if (state.status === "checkmate") {
      const winner = state.turn === "white" ? "Black" : "White";
      return `Checkmate — ${winner} wins`;
    }
    return capitalize(state.status);
  }
  if (state.status === "check") {
    return `${capitalize(state.turn)} to move — in check`;
  }
  return `${capitalize(state.turn)} to move`;
}

function App() {
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [humanColorChoice, setHumanColorChoice] = useState<Color>("white");
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(null);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [aiThinking, setAiThinking] = useState(false);
  const [starting, setStarting] = useState(true);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getState()
      .then(setGameState)
      .catch(() => newGame("white").then(setGameState))
      .finally(() => setStarting(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  useEffect(() => {
    if (!gameState || gameState.game_over) return;
    if (gameState.turn === gameState.human_color) return;

    let cancelled = false;
    setAiThinking(true);
    playAiMove()
      .then((res) => {
        if (cancelled) return;
        setGameState(res.state);
        if (res.uci) setLastMove({ from: res.uci.slice(0, 2), to: res.uci.slice(2, 4) });
        if (!res.ok && res.error) setMoveError(res.error);
        if (res.ok && res.san) {
          const san = res.san;
          explainLastMove()
            .then((comment) => {
              if (cancelled) return;
              setMessages((prev) => [
                ...prev,
                { id: nextId++, role: "assistant", content: `Played ${san}: ${comment}` },
              ]);
            })
            .catch(() => {
              /* commentary is best-effort, ignore failures */
            });
        }
      })
      .catch((err) => {
        if (!cancelled) setMoveError(err instanceof Error ? err.message : "AI move failed");
      })
      .finally(() => {
        if (!cancelled) setAiThinking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [gameState]);

  async function startNewGame(color: Color) {
    setStarting(true);
    setMoveError(null);
    setLastMove(null);
    setMessages([]);
    try {
      const state = await newGame(color);
      setGameState(state);
    } finally {
      setStarting(false);
    }
  }

  async function handleSquareMove(uci: string) {
    setMoveError(null);
    try {
      const res = await playMove(uci);
      if (!res.ok) {
        setMoveError(res.error ?? "Illegal move");
        return;
      }
      setGameState(res.state);
      if (res.uci) setLastMove({ from: res.uci.slice(0, 2), to: res.uci.slice(2, 4) });
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : "Move failed");
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const question = chatInput.trim();
    if (!question || chatLoading) return;

    setMessages((prev) => [...prev, { id: nextId++, role: "user", content: question }]);
    setChatInput("");
    setChatLoading(true);

    try {
      const answer = await askAboutPosition(question);
      setMessages((prev) => [...prev, { id: nextId++, role: "assistant", content: answer }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [...prev, { id: nextId++, role: "error", content: message }]);
    } finally {
      setChatLoading(false);
    }
  }

  const boardDisabled =
    !gameState || gameState.game_over || gameState.turn !== gameState.human_color || aiThinking;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Chess Agents</h1>
        <p>Play against a local LLM, and ask it questions about the position any time.</p>
      </header>

      <div className="app-body">
        <section className="board-column">
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
            <button type="button" onClick={() => startNewGame(humanColorChoice)}>
              New Game
            </button>
          </div>

          {gameState && (
            <>
              <Board
                fen={gameState.fen}
                legalMoves={gameState.legal_moves}
                humanColor={gameState.human_color}
                sideToMove={gameState.turn}
                disabled={boardDisabled || starting}
                lastMove={lastMove}
                onMove={handleSquareMove}
              />
              <div className="game-status">
                <span
                  className={`status-pill status-pill--${gameState.game_over ? "over" : gameState.status}`}
                >
                  {statusLabel(gameState)}
                </span>
                {aiThinking && <span className="status-thinking">AI is thinking…</span>}
              </div>
              {moveError && <div className="move-error">{moveError}</div>}
              {gameState.move_history_san.length > 0 && (
                <pre className="move-history">{formatPgn(gameState.move_history_san)}</pre>
              )}
            </>
          )}
        </section>

        <section className="chat-column">
          <div className="chat-log">
            {messages.length === 0 && (
              <div className="chat-empty">
                Ask about the position — try "what's my best move?" or "is my king safe?"
              </div>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`chat-bubble chat-bubble--${m.role}`}>
                <pre>{m.content}</pre>
              </div>
            ))}
            {chatLoading && (
              <div className="chat-bubble chat-bubble--assistant chat-bubble--pending">
                Thinking…
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <form className="chat-input" onSubmit={handleAsk}>
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Ask about the position…"
              disabled={chatLoading}
            />
            <button type="submit" disabled={chatLoading || !chatInput.trim()}>
              Ask
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}

export default App;
