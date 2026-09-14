import { useEffect, useRef, useState } from "react";
import Board from "./Board";
import {
  askAboutPosition,
  connectGameSocket,
  explainLastMove,
  explainTactic,
  getTactic,
  playAiMove,
  playMove,
  type GameState,
  type TacticInfo,
} from "./api";

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

function lastMoveSquares(state: GameState): { from: string; to: string } | null {
  if (!state.last_move_uci) return null;
  return { from: state.last_move_uci.slice(0, 2), to: state.last_move_uci.slice(2, 4) };
}

interface Props {
  initialState: GameState;
  onExit: () => void;
}

function Game({ initialState, onExit }: Props) {
  const [gameState, setGameState] = useState<GameState>(initialState);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [aiThinking, setAiThinking] = useState(false);
  const [moveInFlight, setMoveInFlight] = useState(false);
  const [tacticInfo, setTacticInfo] = useState<TacticInfo | null>(null);
  const [tacticExplaining, setTacticExplaining] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const gameId = gameState.game_id;
  const isAiMode = gameState.mode === "ai";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  // PvP: receive the opponent's moves over the game's websocket.
  useEffect(() => {
    if (isAiMode) return;
    let cancelled = false;
    let socket: WebSocket | null = null;
    connectGameSocket(gameId).then((s) => {
      if (cancelled) {
        s.close();
        return;
      }
      socket = s;
      s.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "state") setGameState(data.state);
      };
    });
    return () => {
      cancelled = true;
      socket?.close();
    };
  }, [gameId, isAiMode]);

  // AI mode: trigger the engine's reply whenever it's the AI's turn.
  useEffect(() => {
    if (!isAiMode || gameState.game_over) return;
    if (gameState.turn === gameState.human_color) return;

    let cancelled = false;
    setAiThinking(true);
    playAiMove(gameId)
      .then((res) => {
        if (cancelled) return;
        setGameState(res.state);
        if (!res.ok && res.error) setMoveError(res.error);
        if (res.ok && res.san) {
          const san = res.san;
          explainLastMove(gameId)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAiMode, gameId, gameState.turn, gameState.human_color, gameState.game_over]);

  useEffect(() => {
    if (!isAiMode || gameState.game_over) {
      setTacticInfo(null);
      return;
    }
    let cancelled = false;
    getTactic(gameId)
      .then((info) => {
        if (!cancelled) setTacticInfo(info);
      })
      .catch(() => {
        if (!cancelled) setTacticInfo(null);
      });
    return () => {
      cancelled = true;
    };
  }, [isAiMode, gameId, gameState.fen, gameState.game_over]);

  async function handleSquareMove(uci: string) {
    if (moveInFlight) return;
    setMoveError(null);
    setMoveInFlight(true);
    try {
      const res = await playMove(gameId, uci);
      if (!res.ok) {
        setMoveError(res.error ?? "Illegal move");
        return;
      }
      setGameState(res.state);
    } catch (err) {
      setMoveError(err instanceof Error ? err.message : "Move failed");
    } finally {
      setMoveInFlight(false);
    }
  }

  async function handleExplainTactic() {
    if (tacticExplaining) return;
    setTacticExplaining(true);
    try {
      const explanation = await explainTactic(gameId);
      setMessages((prev) => [
        ...prev,
        { id: nextId++, role: "assistant", content: `⚡ ${explanation}` },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [...prev, { id: nextId++, role: "error", content: message }]);
    } finally {
      setTacticExplaining(false);
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
      const answer = await askAboutPosition(gameId, question);
      setMessages((prev) => [...prev, { id: nextId++, role: "assistant", content: answer }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [...prev, { id: nextId++, role: "error", content: message }]);
    } finally {
      setChatLoading(false);
    }
  }

  const boardDisabled =
    gameState.game_over || gameState.turn !== gameState.human_color || aiThinking || moveInFlight;

  return (
    <div className="app-body">
      <section className="board-column">
        <div className="game-controls">
          <span className="opponent-label">
            {isAiMode ? "Playing vs AI" : `Playing vs ${gameState.opponent_name ?? "opponent"}`}
          </span>
          <button type="button" onClick={onExit}>
            Back to lobby
          </button>
        </div>

        <Board
          fen={gameState.fen}
          legalMoves={gameState.legal_moves}
          humanColor={gameState.human_color}
          sideToMove={gameState.turn}
          disabled={boardDisabled}
          lastMove={lastMoveSquares(gameState)}
          attackedSquares={gameState.attacked_squares}
          onMove={handleSquareMove}
        />
        <div className="game-status">
          <span
            className={`status-pill status-pill--${gameState.game_over ? "over" : gameState.status}`}
          >
            {statusLabel(gameState)}
          </span>
          {aiThinking && <span className="status-thinking">AI is thinking…</span>}
          {tacticInfo?.tactic_available && (
            <button
              type="button"
              className="status-tactic"
              onClick={handleExplainTactic}
              disabled={tacticExplaining}
            >
              ⚡ Tactic available for {capitalize(tacticInfo.side)} — {tacticExplaining ? "explaining…" : "explain"}
            </button>
          )}
        </div>
        {moveError && <div className="move-error">{moveError}</div>}
        {gameState.move_history_san.length > 0 && (
          <pre className="move-history">{formatPgn(gameState.move_history_san)}</pre>
        )}
      </section>

      {isAiMode && (
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
      )}
    </div>
  );
}

export default Game;
