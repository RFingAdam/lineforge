/**
 * Shared helpers for the SVG geometry diagrams.
 *
 * Each diagram component reads the current ``geometry`` dict from the
 * Zustand store, parses Length strings (W/H/T/...) to canonical meters,
 * computes layout fractions normalized to its viewBox, and renders a
 * labeled cross-section. Layout is "live" — every form-field change
 * re-runs in <16ms with no debounce needed.
 */

import { toMeters } from "@/lib/units";

/** Parse a geometry-field value to canonical meters. Returns ``fallback``
 * if missing or unparseable. */
export function len(
  geometry: Record<string, unknown> | null,
  field: string,
  fallback: number,
): number {
  if (!geometry) return fallback;
  const raw = geometry[field];
  if (typeof raw === "number") return raw;
  if (typeof raw === "string" && raw.trim() !== "") {
    const m = toMeters(raw);
    if (m !== null && m > 0) return m;
  }
  return fallback;
}

/** Read a numeric field (er, tan_delta) with fallback. */
export function num(
  geometry: Record<string, unknown> | null,
  field: string,
  fallback: number,
): number {
  if (!geometry) return fallback;
  const raw = geometry[field];
  if (typeof raw === "number") return raw;
  if (typeof raw === "string" && raw.trim() !== "") {
    const v = Number(raw);
    if (!Number.isNaN(v)) return v;
  }
  return fallback;
}

/**
 * Color a dielectric region by its εr value. Higher εr → darker. atlc-tinted
 * goldenrod for a neutral "this is a dielectric" feel that contrasts with
 * the red/blue/green conductor palette.
 */
export function dielectricFill(er: number): string {
  // Map εr ∈ [1, 10] → lightness 80% .. 35%
  const clamped = Math.max(1, Math.min(10, er));
  const t = (clamped - 1) / 9; // 0..1
  const lightness = 80 - t * 45; // 80% → 35%
  return `hsl(45 60% ${lightness}%)`;
}

export const PALETTE = {
  signal: "#dc2626", // red — atlc2 +1 (signal)
  signalAlt: "#3b82f6", // blue — atlc2 -1 (return signal in diff pairs)
  ground: "#16a34a", // green — atlc2 0 (ground)
  conductorOutline: "#0a0f17",
  dimension: "#94a3b8", // slate-400 for dimension lines + labels
  dimAccent: "#06b6d4", // cyan-500 for live-edited dimension
  bg: "#0b0f17",
};

/** SVG dimension callout: a horizontal or vertical arrow with a centered
 * label. Used to annotate W, H, T, H1, H2 etc. */
export function DimensionLine({
  x1,
  y1,
  x2,
  y2,
  label,
  color = PALETTE.dimension,
  side = "auto",
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  color?: string;
  side?: "auto" | "above" | "below" | "left" | "right";
}) {
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const horizontal = Math.abs(x2 - x1) > Math.abs(y2 - y1);
  let labelX = cx;
  let labelY = cy;
  let anchor: "start" | "middle" | "end" = "middle";
  if (horizontal) {
    labelY = side === "below" ? cy + 14 : cy - 5;
  } else {
    labelX = side === "right" ? cx + 6 : cx - 6;
    anchor = side === "right" ? "start" : "end";
    labelY = cy + 4;
  }
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth={1} />
      <line
        x1={x1}
        y1={y1 - (horizontal ? 4 : 0)}
        x2={x1}
        y2={y1 + (horizontal ? 4 : 0)}
        stroke={color}
        strokeWidth={1}
      />
      <line
        x1={x2}
        y1={y2 - (horizontal ? 4 : 0)}
        x2={x2}
        y2={y2 + (horizontal ? 4 : 0)}
        stroke={color}
        strokeWidth={1}
      />
      {!horizontal && (
        <>
          <line
            x1={x1 - 4}
            y1={y1}
            x2={x1 + 4}
            y2={y1}
            stroke={color}
            strokeWidth={1}
          />
          <line
            x1={x2 - 4}
            y1={y2}
            x2={x2 + 4}
            y2={y2}
            stroke={color}
            strokeWidth={1}
          />
        </>
      )}
      <text
        x={labelX}
        y={labelY}
        fill={color}
        fontSize={10}
        textAnchor={anchor}
        fontFamily="ui-monospace, SFMono-Regular, monospace"
      >
        {label}
      </text>
    </g>
  );
}

/** Format a length-in-meters value back to a user-readable string with
 * the user's preferred unit. Used for diagram labels. */
export function formatDim(meters: number, unit: "mil" | "mm" | "in" | "um"): string {
  const m = meters;
  if (unit === "mil") return `${(m / 25.4e-6).toFixed(2)}mil`;
  if (unit === "mm") return `${(m * 1000).toFixed(3)}mm`;
  if (unit === "in") return `${(m / 25.4e-3).toFixed(4)}in`;
  return `${(m * 1e6).toFixed(1)}µm`;
}
