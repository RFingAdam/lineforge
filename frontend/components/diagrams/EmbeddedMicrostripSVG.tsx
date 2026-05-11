"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

export function EmbeddedMicrostripSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 6 * 25.4e-6);
  const H = len(geometry, "H", 4 * 25.4e-6);
  const H2 = len(geometry, "H2", 2 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const er = num(geometry, "er", 4.4);
  const er2 = num(geometry, "er2", 1.0);

  const PAD = 60;
  const VW = 400;
  const VH = 240;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  const totalY = H + T + H2;
  const yScale = PLOT_H / totalY;
  const xScale = PLOT_W / Math.max(W * 4, totalY * 1.5);

  const groundY = PAD + PLOT_H;
  const lowerTop = groundY - H * yScale;
  const stripTop = lowerTop - T * yScale;
  const upperTop = stripTop - H2 * yScale;
  const stripCx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const stripX = stripCx - stripW / 2;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      <rect
        x={PAD}
        y={upperTop}
        width={PLOT_W}
        height={H2 * yScale}
        fill={dielectricFill(er2)}
        opacity={0.7}
      />
      <rect
        x={PAD}
        y={stripTop}
        width={PLOT_W}
        height={T * yScale}
        fill={dielectricFill(er)}
        opacity={0.7}
      />
      <rect
        x={PAD}
        y={lowerTop}
        width={PLOT_W}
        height={H * yScale}
        fill={dielectricFill(er)}
        opacity={0.7}
      />
      <rect x={PAD} y={groundY} width={PLOT_W} height={6} fill={PALETTE.ground} />
      <rect
        x={stripX}
        y={stripTop}
        width={stripW}
        height={T * yScale}
        fill={PALETTE.signal}
      />

      <text x={PAD + 6} y={upperTop + 12} fontSize={9} fill={PALETTE.conductorOutline}>
        εr2={er2.toFixed(2)}
      </text>
      <text x={PAD + 6} y={lowerTop + 12} fontSize={9} fill={PALETTE.conductorOutline}>
        εr={er.toFixed(2)}
      </text>
      <DimensionLine
        x1={stripX}
        y1={stripTop - 12}
        x2={stripX + stripW}
        y2={stripTop - 12}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={lowerTop}
        x2={PAD - 22}
        y2={groundY}
        label={`H = ${formatDim(H, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={PAD - 22}
        y1={upperTop}
        x2={PAD - 22}
        y2={stripTop}
        label={`H₂ = ${formatDim(H2, unit)}`}
        side="left"
      />
    </svg>
  );
}
