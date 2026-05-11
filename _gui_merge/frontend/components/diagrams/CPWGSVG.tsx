"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

export function CPWGSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 5 * 25.4e-6);
  const S = len(geometry, "S", 4 * 25.4e-6);
  const H = len(geometry, "H", 8 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const er = num(geometry, "er", 4.4);

  const PAD = 60;
  const VW = 440;
  const VH = 220;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  const totalY = H + T;
  const yScale = PLOT_H / totalY;
  const totalX = W + 2 * S + 2 * Math.max(W, S * 2);
  const xScale = PLOT_W / totalX;

  const groundY = PAD + PLOT_H;
  const dielTop = groundY - H * yScale;
  const stripTop = dielTop - T * yScale;
  const stripCx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const stripX = stripCx - stripW / 2;
  const sx = S * xScale;
  const leftGroundX = stripX - sx - Math.max(stripW, 30);
  const rightGroundX = stripX + stripW + sx;
  const sideGroundW = Math.max(stripW, 30);

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      <rect x={PAD} y={groundY} width={PLOT_W} height={6} fill={PALETTE.ground} />
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

      {/* coplanar grounds */}
      <rect x={leftGroundX} y={stripTop} width={sideGroundW} height={T * yScale} fill={PALETTE.ground} />
      <rect x={rightGroundX} y={stripTop} width={sideGroundW} height={T * yScale} fill={PALETTE.ground} />
      {/* signal */}
      <rect x={stripX} y={stripTop} width={stripW} height={T * yScale} fill={PALETTE.signal} />

      <DimensionLine
        x1={stripX}
        y1={stripTop - 14}
        x2={stripX + stripW}
        y2={stripTop - 14}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={stripX + stripW}
        y1={stripTop - 22}
        x2={stripX + stripW + sx}
        y2={stripTop - 22}
        label={`S = ${formatDim(S, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={dielTop}
        x2={PAD - 22}
        y2={groundY}
        label={`H = ${formatDim(H, unit)}`}
        side="left"
      />
    </svg>
  );
}
