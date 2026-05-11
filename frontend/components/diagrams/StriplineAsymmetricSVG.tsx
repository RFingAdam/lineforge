"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

/**
 * Asymmetric stripline cross-section.
 *
 * Layout (top-to-bottom):
 *   [ ground plane top  ]
 *   [ dielectric H1     ] ← εr_above (or εr if no split)
 *   [ strip W × T       ]
 *   [ dielectric H2     ] ← εr_below
 *   [ ground plane bot  ]
 *
 * If er_above ≠ er_below the two halves get distinct fills; otherwise they
 * share the bulk er color.
 */
export function StriplineAsymmetricSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 5 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const H1 = len(geometry, "H1", 3 * 25.4e-6);
  const H2 = len(geometry, "H2", 9 * 25.4e-6);
  const erBulk = num(geometry, "er", 4.4);
  const erAbove = num(geometry, "er_above", erBulk);
  const erBelow = num(geometry, "er_below", erBulk);
  const splitEr = (geometry?.er_above ?? null) !== null || (geometry?.er_below ?? null) !== null;

  const PAD = 60;
  const VW = 400;
  const VH = 280;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;

  const totalY = H1 + T + H2;
  const yScale = PLOT_H / totalY;
  const xMax = Math.max(W * 4, totalY * 1.5);
  const xScale = PLOT_W / xMax;

  const topGround = PAD;
  const h1Bot = topGround + H1 * yScale;
  const stripTop = h1Bot;
  const stripBot = stripTop + T * yScale;
  const botGround = stripBot + H2 * yScale;

  const stripCx = PAD + PLOT_W / 2;
  const stripW = W * xScale;
  const stripX = stripCx - stripW / 2;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      {/* dielectric above */}
      <rect
        x={PAD}
        y={topGround}
        width={PLOT_W}
        height={H1 * yScale}
        fill={dielectricFill(erAbove)}
        opacity={0.7}
      />
      <text
        x={PAD + 6}
        y={topGround + (H1 * yScale) / 2}
        fontSize={9}
        fill={PALETTE.conductorOutline}
        fontFamily="ui-monospace, monospace"
      >
        εr={erAbove.toFixed(2)}
      </text>

      {/* strip-row dielectric (uses below color so no visual seam) */}
      <rect
        x={PAD}
        y={stripTop}
        width={PLOT_W}
        height={T * yScale}
        fill={dielectricFill(erBelow)}
        opacity={0.7}
      />

      {/* dielectric below */}
      <rect
        x={PAD}
        y={stripBot}
        width={PLOT_W}
        height={H2 * yScale}
        fill={dielectricFill(erBelow)}
        opacity={0.7}
      />
      <text
        x={PAD + 6}
        y={stripBot + (H2 * yScale) / 2}
        fontSize={9}
        fill={PALETTE.conductorOutline}
        fontFamily="ui-monospace, monospace"
      >
        εr={erBelow.toFixed(2)}
      </text>

      {/* ground planes */}
      <rect x={PAD} y={topGround - 4} width={PLOT_W} height={4} fill={PALETTE.ground} />
      <rect x={PAD} y={botGround} width={PLOT_W} height={4} fill={PALETTE.ground} />
      <text x={PAD + 4} y={topGround - 7} fontSize={9} fill={PALETTE.ground}>
        ground
      </text>
      <text x={PAD + 4} y={botGround + 14} fontSize={9} fill={PALETTE.ground}>
        ground
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

      {/* dimensions */}
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
        y2={h1Bot}
        label={`H₁ = ${formatDim(H1, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={PAD - 22}
        y1={stripBot}
        x2={PAD - 22}
        y2={botGround}
        label={`H₂ = ${formatDim(H2, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={VW - PAD + 22}
        y1={stripTop}
        x2={VW - PAD + 22}
        y2={stripBot}
        label={`T = ${formatDim(T, unit)}`}
        side="right"
      />

      {splitEr && (
        <text
          x={VW - PAD - 4}
          y={topGround + 12}
          fontSize={9}
          fill={PALETTE.dimAccent}
          textAnchor="end"
          fontFamily="ui-monospace, monospace"
        >
          split-εr
        </text>
      )}
    </svg>
  );
}
