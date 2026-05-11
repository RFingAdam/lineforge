"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

/**
 * Edge-coupled differential pair (microstrip or stripline variant via the
 * ``stripline`` prop). Two parallel signal traces with edge-to-edge gap S.
 */
export function DiffPairSVG({
  geometry,
  unit,
  stripline = false,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
  stripline?: boolean;
}) {
  const W = len(geometry, "W", 4 * 25.4e-6);
  const S = len(geometry, "S", 6 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const H = len(geometry, "H", 4 * 25.4e-6);
  const B = len(geometry, "B", 14 * 25.4e-6);
  const er = num(geometry, "er", 4.4);

  const PAD = 60;
  const VW = 440;
  const VH = 240;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  const totalY = stripline ? B : H + T;
  const yScale = PLOT_H / totalY;
  const totalX = 2 * W + S + Math.max(W, S);
  const xScale = PLOT_W / totalX;

  const groundY = PAD + PLOT_H;
  let stripTop: number;
  let topGroundY: number | null = null;
  if (stripline) {
    topGroundY = PAD;
    const cy = (PAD + groundY) / 2;
    stripTop = cy - (T * yScale) / 2;
  } else {
    const dielTop = groundY - H * yScale;
    stripTop = dielTop - T * yScale;
  }
  const cx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const sx = S * xScale;
  const leftX = cx - sx / 2 - stripW;
  const rightX = cx + sx / 2;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      {/* dielectric */}
      <rect
        x={PAD}
        y={stripline ? topGroundY! : groundY - H * yScale}
        width={PLOT_W}
        height={stripline ? B * yScale : H * yScale}
        fill={dielectricFill(er)}
        opacity={0.7}
      />
      {/* grounds */}
      <rect x={PAD} y={groundY} width={PLOT_W} height={4} fill={PALETTE.ground} />
      {stripline && topGroundY !== null && (
        <rect x={PAD} y={topGroundY - 4} width={PLOT_W} height={4} fill={PALETTE.ground} />
      )}
      {/* two signal strips */}
      <rect x={leftX} y={stripTop} width={stripW} height={T * yScale} fill={PALETTE.signal} />
      <rect x={rightX} y={stripTop} width={stripW} height={T * yScale} fill={PALETTE.signalAlt} />
      <text x={leftX + stripW / 2} y={stripTop - 4} fontSize={9} fill={PALETTE.signal} textAnchor="middle">
        +
      </text>
      <text x={rightX + stripW / 2} y={stripTop - 4} fontSize={9} fill={PALETTE.signalAlt} textAnchor="middle">
        −
      </text>

      <DimensionLine
        x1={leftX}
        y1={stripTop - 18}
        x2={leftX + stripW}
        y2={stripTop - 18}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={leftX + stripW}
        y1={stripTop - 30}
        x2={rightX}
        y2={stripTop - 30}
        label={`S = ${formatDim(S, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={stripline ? topGroundY! : groundY - H * yScale}
        x2={PAD - 22}
        y2={groundY}
        label={stripline ? `B = ${formatDim(B, unit)}` : `H = ${formatDim(H, unit)}`}
        side="left"
      />
    </svg>
  );
}
