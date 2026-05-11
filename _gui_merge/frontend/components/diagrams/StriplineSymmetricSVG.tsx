"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

export function StriplineSymmetricSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 5 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const B = len(geometry, "B", 14 * 25.4e-6);
  const er = num(geometry, "er", 4.4);

  const PAD = 60;
  const VW = 400;
  const VH = 240;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  const yScale = PLOT_H / B;
  const xMax = Math.max(W * 4, B * 1.5);
  const xScale = PLOT_W / xMax;

  const topGround = PAD;
  const botGround = PAD + B * yScale;
  const stripCy = (topGround + botGround) / 2;
  const stripTop = stripCy - (T * yScale) / 2;
  const stripCx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const stripX = stripCx - stripW / 2;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      {/* dielectric */}
      <rect
        x={PAD}
        y={topGround}
        width={PLOT_W}
        height={botGround - topGround}
        fill={dielectricFill(er)}
        opacity={0.7}
      />
      <text
        x={PAD + 6}
        y={topGround + 12}
        fontSize={9}
        fill={PALETTE.conductorOutline}
        fontFamily="ui-monospace, monospace"
      >
        εr={er.toFixed(2)}
      </text>
      {/* grounds */}
      <rect x={PAD} y={topGround - 4} width={PLOT_W} height={4} fill={PALETTE.ground} />
      <rect x={PAD} y={botGround} width={PLOT_W} height={4} fill={PALETTE.ground} />
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
      <DimensionLine
        x1={stripX}
        y1={stripTop - 12}
        x2={stripX + stripW}
        y2={stripTop - 12}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={topGround}
        x2={PAD - 22}
        y2={botGround}
        label={`B = ${formatDim(B, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={VW - PAD + 22}
        y1={stripTop}
        x2={VW - PAD + 22}
        y2={stripTop + T * yScale}
        label={`T = ${formatDim(T, unit)}`}
        side="right"
      />
    </svg>
  );
}
