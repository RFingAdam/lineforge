"use client";

import { DimensionLine, PALETTE, dielectricFill, formatDim, len, num } from "./utils";

/** Broadside-coupled diff stripline: two strips stacked vertically inside
 * the dielectric cavity, with H_between separating them. */
export function BroadsideCoupledSVG({
  geometry,
  unit,
}: {
  geometry: Record<string, unknown> | null;
  unit: "mil" | "mm" | "in" | "um";
}) {
  const W = len(geometry, "W", 4 * 25.4e-6);
  const T = len(geometry, "T", 1.4 * 25.4e-6);
  const H1 = len(geometry, "H1", 4 * 25.4e-6);
  const Hbet = len(geometry, "H_between", 6 * 25.4e-6);
  const er = num(geometry, "er", 4.4);

  const totalY = 2 * H1 + 2 * T + Hbet;
  const PAD = 60;
  const VW = 400;
  const VH = 280;
  const PLOT_W = VW - 2 * PAD;
  const PLOT_H = VH - 2 * PAD;
  const yScale = PLOT_H / totalY;
  const xScale = PLOT_W / Math.max(W * 4, totalY * 1.5);

  const topG = PAD;
  const topStripTop = topG + H1 * yScale;
  const topStripBot = topStripTop + T * yScale;
  const botStripTop = topStripBot + Hbet * yScale;
  const botStripBot = botStripTop + T * yScale;
  const botG = botStripBot + H1 * yScale;
  const cx = PAD + PLOT_W / 2;
  const stripW = W * xScale;

  return (
    <svg viewBox={`0 0 ${VW} ${VH}`} className="w-full h-auto bg-navy-950 rounded">
      <rect x={PAD} y={topG} width={PLOT_W} height={botG - topG} fill={dielectricFill(er)} opacity={0.7} />
      <rect x={PAD} y={topG - 4} width={PLOT_W} height={4} fill={PALETTE.ground} />
      <rect x={PAD} y={botG} width={PLOT_W} height={4} fill={PALETTE.ground} />
      <rect x={cx - stripW / 2} y={topStripTop} width={stripW} height={T * yScale} fill={PALETTE.signal} />
      <rect x={cx - stripW / 2} y={botStripTop} width={stripW} height={T * yScale} fill={PALETTE.signalAlt} />

      <DimensionLine
        x1={cx - stripW / 2}
        y1={topStripTop - 12}
        x2={cx + stripW / 2}
        y2={topStripTop - 12}
        label={`W = ${formatDim(W, unit)}`}
      />
      <DimensionLine
        x1={PAD - 22}
        y1={topG}
        x2={PAD - 22}
        y2={topStripTop}
        label={`H₁ = ${formatDim(H1, unit)}`}
        side="left"
      />
      <DimensionLine
        x1={PAD - 22}
        y1={topStripBot}
        x2={PAD - 22}
        y2={botStripTop}
        label={`H_between = ${formatDim(Hbet, unit)}`}
        side="left"
      />
      <text x={PAD + 6} y={topG + 12} fontSize={9} fill={PALETTE.conductorOutline} fontFamily="ui-monospace, monospace">
        εr={er.toFixed(2)}
      </text>
    </svg>
  );
}
