import type { JSX } from "react";
import type { Color } from "./api";

export type PieceType = "k" | "q" | "r" | "b" | "n" | "p";

interface ShapeProps {
  fill: string;
  stroke: string;
}

const FILL: Record<Color, string> = { white: "#f5f5f0", black: "#1a1a1a" };
const STROKE: Record<Color, string> = { white: "#1a1a1a", black: "#f5f5f0" };

function Pawn({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <circle cx="22.5" cy="12" r="6.5" />
      <path d="M17 20 L28 20 L32 36 L13 36 Z" />
      <rect x="10" y="36" width="25" height="4" rx="1" />
    </g>
  );
}

function Rook({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <rect x="12" y="10" width="4.5" height="6" />
      <rect x="20.25" y="10" width="4.5" height="6" />
      <rect x="28.5" y="10" width="4.5" height="6" />
      <rect x="11" y="14" width="23" height="4" />
      <path d="M14 18 L31 18 L29 34 L16 34 Z" />
      <rect x="10" y="34" width="25" height="4" rx="1" />
    </g>
  );
}

function Knight({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <path d="M32 36 C32 30 30 27 30 24 C33 22 34 18 32 14 C30 10 25 8 21 9 C21 9 20 6 17 6 C15 6 14 8 15 10 C11 11 8 15 8 20 C8 24 10 25 10 28 L10 36 Z" />
      <circle cx="17.5" cy="13.5" r="1" fill={stroke} stroke="none" />
    </g>
  );
}

function Bishop({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <circle cx="22.5" cy="8" r="2.5" />
      <path d="M22.5 12 C27 12 30 16 29 21 C28.5 24 26 25 26 27 C29 28 31 31 31 34 L14 34 C14 31 16 28 19 27 C19 25 16.5 24 16 21 C15 16 18 12 22.5 12 Z" />
      <rect x="19" y="20" width="7" height="2" fill={stroke} stroke="none" />
      <rect x="10" y="34" width="25" height="4" rx="1" />
    </g>
  );
}

function Queen({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <circle cx="10" cy="10" r="2.2" />
      <circle cx="17.5" cy="7" r="2.2" />
      <circle cx="22.5" cy="6" r="2.2" />
      <circle cx="27.5" cy="7" r="2.2" />
      <circle cx="35" cy="10" r="2.2" />
      <path d="M10 12 L35 12 L32 26 C29 25 27 26 27 28 C25 26.5 22.5 26.5 22.5 28 C22.5 26.5 20 26.5 18 28 C18 26 16 25 13 26 Z" />
      <rect x="9" y="34" width="27" height="4" rx="1" />
    </g>
  );
}

function King({ fill, stroke }: ShapeProps) {
  return (
    <g fill={fill} stroke={stroke} strokeWidth={1.5} strokeLinejoin="round">
      <rect x="21" y="2" width="3" height="7" />
      <rect x="18" y="4.5" width="9" height="3" />
      <path d="M22.5 11 C27 11 30 14 29 19 C28.5 22 26 23 26 25 C29 26 31 29 31 32 L14 32 C14 29 16 26 19 25 C19 23 16.5 22 16 19 C15 14 18 11 22.5 11 Z" />
      <rect x="10" y="32" width="25" height="4" rx="1" />
    </g>
  );
}

const SHAPES: Record<PieceType, (p: ShapeProps) => JSX.Element> = {
  p: Pawn,
  r: Rook,
  n: Knight,
  b: Bishop,
  q: Queen,
  k: King,
};

interface PieceIconProps {
  type: PieceType;
  color: Color;
  className?: string;
}

export default function PieceIcon({ type, color, className }: PieceIconProps) {
  const Shape = SHAPES[type];
  return (
    <svg viewBox="0 0 45 45" className={className} aria-hidden="true" focusable="false">
      <Shape fill={FILL[color]} stroke={STROKE[color]} />
    </svg>
  );
}
