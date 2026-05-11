"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

/**
 * Microstrip cross-section: a strip on top of a dielectric over a ground plane.
 * Layout (SVG coords, top-down):
 *   [ air margin       ] ← top
 *   [ strip (W × T)    ]
 *   [ dielectric (H)   ] ← εr-tinted
 *   [ ground plane     ] ← bottom
 */
export function MicrostripSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 6 * 25.4e-6);
  const H = len(geometry, "H", 4 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const er = num(geometry, "er", 4.4);

  // SVG layout: viewBox 400 × 220, with 60 px padding for dim callouts.
  const PAD = 60;
  const VW = 400;
  const VH = 220;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  // Vertical scale: H + T fit in PLOT_H. Strip width: scaled relative to PLOT_W.
  const totalY = H + T;
  const yScale = PLOT_H / totalY;
  const xMax = Math.max(W * 4, totalY * 2); // a little margin around the strip
  const xScale = PLOT_W / xMax;

  const groundY = PAD + PLOT_H;
  const dielTop = groundY - H * yScale;
  const stripTop = dielTop - T * yScale;
  const stripCx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const stripX = stripCx - stripW / 2;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      {/* ground plane */}
      <rect x={PAD} y={groundY} width={PLOT_W} height={6} fill={PALETTE.ground} />
      <text x={PAD + 4} y={groundY + 18} fontSize={9} fill={PALETTE.ground}>
        ground
      </text>
      {/* dielectric */}
      <rect
        x={PAD}
        y={dielTop}
        width={PLOT_W}
        height={H * yScale}
        fill={dielectricFill(er)}
        opacity={0.7}
      />
      <text
        x={PAD + 6}
        y={dielTop + 12}
        fontSize={9}
        fill={PALETTE.conductorOutline}
        fontFamily="ui-monospace, monospace"
      >
        εr={er.toFixed(2)}
      </text>
      {/* strip */}
      <rect
        x={stripX}
        y={stripTop}
        width={stripW}
        height={T * yScale}
        fill={PALETTE.signal}
        stroke={PALETTE.conductorOutline}
        strokeWidth={0.5}
      />
      <text x={stripCx} y={stripTop - 4} fontSize={9} fill={PALETTE.signal} textAnchor="middle">
        signal
      </text>

      {/* dimensions */}
      <DimensionLine
        x1={stripX}
        y1={stripTop - 22}
        x2={stripX + stripW}
        y2={stripTop - 22}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={dielTop}
        x2={PAD - 22}
        y2={groundY}
        label={`H = ${formatDim(H, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={VW - PAD + 22}
        y1={stripTop}
        x2={VW - PAD + 22}
        y2={dielTop}
        label={`T = ${formatDim(T, unit)}`}
        side="right"
      />
    </svg>
  );
}
