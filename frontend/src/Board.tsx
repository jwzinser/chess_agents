import { useMemo, useState } from "react";
import type { Color, LegalMove } from "./api";
import "./Board.css";

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];

const UNICODE_PIECES: Record<string, string> = {
  K: "♔",
  Q: "♕",
  R: "♖",
  B: "♗",
  N: "♘",
  P: "♙",
  k: "♚",
  q: "♛",
  r: "♜",
  b: "♝",
  n: "♞",
  p: "♟",
};

function piecesBySquare(fen: string): Record<string, string> {
  const board = fen.split(" ")[0];
  const pieces: Record<string, string> = {};
  board.split("/").forEach((row, rankFromTop) => {
    let file = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) {
        file += Number(ch);
      } else {
        const rank = 8 - rankFromTop;
        pieces[`${FILES[file]}${rank}`] = ch;
        file += 1;
      }
    }
  });
  return pieces;
}

interface Props {
  fen: string;
  legalMoves: LegalMove[];
  humanColor: Color;
  sideToMove: Color;
  disabled: boolean;
  lastMove?: { from: string; to: string } | null;
  onMove: (uci: string) => void;
}

export default function Board({
  fen,
  legalMoves,
  humanColor,
  sideToMove,
  disabled,
  lastMove,
  onMove,
}: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const pieces = useMemo(() => piecesBySquare(fen), [fen]);
  const flipped = humanColor === "black";

  const legalTargets = useMemo(() => {
    if (!selected) return new Map<string, LegalMove>();
    const map = new Map<string, LegalMove>();
    for (const m of legalMoves) {
      if (m.uci.startsWith(selected)) map.set(m.uci.slice(2, 4), m);
    }
    return map;
  }, [selected, legalMoves]);

  function squareColorOf(piece: string | undefined): Color | null {
    if (!piece) return null;
    return piece === piece.toUpperCase() ? "white" : "black";
  }

  function handleClick(square: string) {
    if (disabled) return;
    const piece = pieces[square];

    if (!selected) {
      if (squareColorOf(piece) === sideToMove) setSelected(square);
      return;
    }

    if (square === selected) {
      setSelected(null);
      return;
    }

    if (squareColorOf(piece) === sideToMove) {
      setSelected(square);
      return;
    }

    const target = legalTargets.get(square);
    if (target) {
      // Multiple legal moves can share a from/to (pawn promotion choices);
      // always auto-promote to queen to keep the UI simple.
      const queenPromo = legalMoves.find(
        (m) => m.uci.startsWith(`${selected}${square}`) && m.uci.endsWith("q"),
      );
      onMove((queenPromo ?? target).uci);
    }
    setSelected(null);
  }

  const cells = [];
  for (let i = 0; i < 8; i++) {
    for (let j = 0; j < 8; j++) {
      const boardRankIdx = flipped ? 7 - i : i;
      const boardFileIdx = flipped ? 7 - j : j;
      const rank = 8 - boardRankIdx;
      const file = FILES[boardFileIdx];
      const square = `${file}${rank}`;
      const piece = pieces[square];
      const dark = (boardRankIdx + boardFileIdx) % 2 === 1;
      const isSelected = square === selected;
      const isTarget = legalTargets.has(square);
      const isLastMove = lastMove?.from === square || lastMove?.to === square;

      cells.push(
        <button
          key={square}
          type="button"
          className={[
            "board-square",
            dark ? "board-square--dark" : "board-square--light",
            isSelected ? "board-square--selected" : "",
            isLastMove ? "board-square--last-move" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={() => handleClick(square)}
          aria-label={square}
        >
          {piece && <span className="board-piece">{UNICODE_PIECES[piece]}</span>}
          {isTarget && !piece && <span className="board-dot" />}
          {isTarget && piece && <span className="board-ring" />}
        </button>,
      );
    }
  }

  return <div className="board-grid">{cells}</div>;
}
