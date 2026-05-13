"use client";

import { useMemo, useState } from "react";
import { runSweep, type SweepPoint } from "@/lib/api";
import { useGuiStore } from "@/lib/store";
import { Button, Card, Input, Select } from "@/components/ui";
import {
  type Metric,
  METRIC_LABEL,
  METRIC_AXIS_LABEL,
  xAxisLabel,
  logDecades,
  logMinors,
  linearMinors,
  fmtX,
  fmtY,
  fmtReadX,
  fmtReadY,
} from "./_sweepChartHelpers";

/**
 * Hand-rolled SVG line chart. No charting-lib dep.
 *
 * Plots one of (z0 / eps_eff / dielectric_loss_db_per_in) on y vs the
 * sweep parameter on x. Frequency sweeps use log-x; geometry sweeps use
 * linear-x. Hover shows a crosshair + readout with point values.
 */
export function SweepChart() {
  const geometry = useGuiStore((s) => s.geometry);
  const sweepConfig = useGuiStore((s) => s.sweepConfig);
  const sweepResults = useGuiStore((s) => s.sweepResults);
  const setSweepConfig = useGuiStore((s) => s.setSweepConfig);
  const setSweepResults = useGuiStore((s) => s.setSweepResults);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("z0");
  const [parameter, setParameter] = useState("frequency");
  const [start, setStart] = useState("1e8");
  const [stop, setStop] = useState("2e10");
  const [n, setN] = useState(31);

  async function run() {
    if (!geometry) return;
    setBusy(true);
    setErr(null);
    try {
      const lo = parseFloat(start);
      const hi = parseFloat(stop);
      if (Number.isNaN(lo) || Number.isNaN(hi) || lo <= 0 || hi <= lo) {
        throw new Error("invalid sweep range");
      }
      const values: number[] = [];
      if (parameter === "frequency") {
        // Log-spaced for frequency — preserves decade structure across
        // the standard 100 MHz – 20 GHz RF window.
        const lLo = Math.log10(lo);
        const lHi = Math.log10(hi);
        for (let i = 0; i < n; i++) values.push(Math.pow(10, lLo + (i * (lHi - lLo)) / (n - 1)));
      } else {
        for (let i = 0; i < n; i++) values.push(lo + (i * (hi - lo)) / (n - 1));
      }
      const resp = await runSweep({ geometry, parameter, values });
      setSweepConfig({ parameter, values, solver: "analytical" });
      setSweepResults(resp.points);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function exportTouchstone() {
    if (!geometry || !sweepConfig || sweepConfig.parameter !== "frequency") return;
    setBusy(true);
    setErr(null);
    try {
      const resp = await runSweep({
        geometry,
        parameter: sweepConfig.parameter,
        values: sweepConfig.values,
        touchstone_out: "trace.s2p",
        line_length: "1in",
        z_ref: 50.0,
      });
      if (resp.touchstone_error) throw new Error(resp.touchstone_error);
      const ts = resp.touchstone as { filename: string; content: string } | undefined;
      if (!ts) throw new Error("backend returned no touchstone payload");
      const blob = new Blob([ts.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = ts.filename || "trace.s2p";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const series = useMemo(
    () => buildSeries(sweepResults, sweepConfig?.parameter, metric),
    [sweepResults, sweepConfig?.parameter, metric],
  );
  const canExport = sweepConfig?.parameter === "frequency" && (sweepResults?.length ?? 0) >= 2;
  const activeParameter = sweepConfig?.parameter ?? parameter;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Sweep</div>
        <Button
          variant="ghost"
          size="sm"
          onClick={exportTouchstone}
          disabled={!canExport || busy}
          title={canExport ? "Re-run sweep with Touchstone export and download .s2p" : "Run a frequency sweep first"}
          leftIcon={<DownloadIcon />}
        >
          .s2p
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Select label="Parameter" value={parameter} onChange={(e) => setParameter(e.target.value)}>
          <option value="frequency">frequency</option>
          <option value="W">W</option>
          <option value="H">H</option>
          <option value="T">T</option>
          <option value="er">er</option>
        </Select>
        <Select label="Y-axis" value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
          <option value="z0">{METRIC_LABEL.z0}</option>
          <option value="eps_eff">{METRIC_LABEL.eps_eff}</option>
          <option value="dielectric_loss_db_per_in">{METRIC_LABEL.dielectric_loss_db_per_in}</option>
        </Select>
        <Input label="Start" value={start} onChange={(e) => setStart(e.target.value)} className="font-mono" />
        <Input label="Stop" value={stop} onChange={(e) => setStop(e.target.value)} className="font-mono" />
        <Input
          label="Points"
          type="number"
          value={n}
          onChange={(e) => setN(Math.max(2, Math.min(401, parseInt(e.target.value) || 31)))}
          className="font-mono"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={run}
          disabled={!geometry || busy}
          loading={busy}
          className="self-end"
        >
          {busy ? "Sweeping…" : "Run sweep"}
        </Button>
      </div>

      {err && (
        <div className="bg-danger/10 border border-danger/40 rounded-sm p-2 text-xs text-danger">{err}</div>
      )}

      {series ? (
        <Card tone="raised" padded={false} className="overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle">
            <div className="text-[11px] uppercase tracking-wider text-slate-400">
              {METRIC_AXIS_LABEL[metric]}
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-slate-300">
              <span className="inline-block w-3 h-0.5 bg-accent-strong rounded-full" />
              <span className="font-mono text-slate-400">{METRIC_LABEL[metric]}</span>
            </div>
          </div>
          <ChartSVG series={series} metric={metric} parameter={activeParameter} />
        </Card>
      ) : !busy ? (
        <Card tone="raised" className="flex items-center justify-center text-slate-500 text-sm h-40">
          {geometry ? "Run a sweep to see results" : "Configure a geometry on the left, then run a sweep."}
        </Card>
      ) : null}
    </div>
  );
}

function buildSeries(
  points: SweepPoint[] | null,
  parameter: string | undefined,
  metric: Metric,
): { x: number[]; y: number[]; xLog: boolean } | null {
  if (!points || !parameter || points.length === 0) return null;
  const xs: number[] = [];
  const ys: number[] = [];
  for (const p of points) {
    const x = p.params[parameter];
    const y = p.result?.[metric];
    if (typeof x === "number" && typeof y === "number" && !Number.isNaN(y)) {
      xs.push(x);
      ys.push(y);
    }
  }
  if (xs.length < 2) return null;
  return { x: xs, y: ys, xLog: parameter === "frequency" };
}

interface Hover { i: number; sx: number; sy: number }

function ChartSVG({
  series,
  metric,
  parameter,
}: {
  series: { x: number[]; y: number[]; xLog: boolean };
  metric: Metric;
  parameter: string;
}) {
  const W = 460, H = 260, PAD_L = 64, PAD_R = 16, PAD_T = 14, PAD_B = 48;
  const [hover, setHover] = useState<Hover | null>(null);

  const xMin = Math.min(...series.x);
  const xMax = Math.max(...series.x);
  const yMin = Math.min(...series.y);
  const yMax = Math.max(...series.y);
  const yPad = (yMax - yMin) * 0.08 || Math.abs(yMax) * 0.05 || 1;
  const yLo = yMin - yPad;
  const yHi = yMax + yPad;

  const sx = (x: number) => {
    if (series.xLog) {
      const t = (Math.log10(x) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin));
      return PAD_L + t * (W - PAD_L - PAD_R);
    }
    return PAD_L + ((x - xMin) / (xMax - xMin)) * (W - PAD_L - PAD_R);
  };
  const sy = (y: number) => H - PAD_B - ((y - yLo) / (yHi - yLo)) * (H - PAD_T - PAD_B);

  const path = series.x
    .map((x, i) => `${i === 0 ? "M" : "L"} ${sx(x).toFixed(2)} ${sy(series.y[i]).toFixed(2)}`)
    .join(" ");

  const yMajor = [0, 0.25, 0.5, 0.75, 1].map((t) => yLo + t * (yHi - yLo));
  const yMinor: number[] = linearMinors(yMajor);
  const xMajor: number[] = series.xLog
    ? logDecades(xMin, xMax)
    : [0, 0.25, 0.5, 0.75, 1].map((t) => xMin + t * (xMax - xMin));
  const xMinor: number[] = series.xLog ? logMinors(xMin, xMax) : linearMinors(xMajor);

  function onMove(e: React.MouseEvent<SVGRectElement>) {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    // SVG preserves aspect ratio (xMidYMid meet) so x scales linearly.
    const mx = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0, bestDist = Infinity;
    for (let i = 0; i < series.x.length; i++) {
      const dx = Math.abs(sx(series.x[i]) - mx);
      if (dx < bestDist) { bestDist = dx; best = i; }
    }
    setHover({ i: best, sx: sx(series.x[best]), sy: sy(series.y[best]) });
  }

  const readoutW = 130, readoutH = 38;
  const readoutX = W - PAD_R - readoutW, readoutY = PAD_T + 4;
  const xTitleY = H - 8, xTitleX = (PAD_L + (W - PAD_R)) / 2;
  const yTitleX = 14, yTitleY = (PAD_T + (H - PAD_B)) / 2;
  const tickClass = "fill-slate-300 font-mono";
  const titleClass = "fill-slate-300 font-medium";

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-auto block"
      role="img"
      aria-label={`${METRIC_AXIS_LABEL[metric]} versus ${xAxisLabel(parameter)} sweep`}
    >
      <rect x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={H - PAD_T - PAD_B} className="fill-canvas" />

      {/* minor grid (drawn first so majors paint over) */}
      {yMinor.map((y, i) => (
        <line key={`yn${i}`} x1={PAD_L} y1={sy(y)} x2={W - PAD_R} y2={sy(y)}
          className="stroke-border-subtle/40" strokeWidth={0.5} />
      ))}
      {xMinor.map((x, i) => x > xMin && x < xMax ? (
        <line key={`xn${i}`} x1={sx(x)} y1={PAD_T} x2={sx(x)} y2={H - PAD_B}
          className="stroke-border-subtle/40" strokeWidth={0.5} />
      ) : null)}

      {/* major grid + y-tick labels */}
      {yMajor.map((y, i) => (
        <g key={`y${i}`}>
          <line x1={PAD_L} y1={sy(y)} x2={W - PAD_R} y2={sy(y)}
            className="stroke-border-subtle" strokeDasharray="2 3" />
          <text x={PAD_L - 8} y={sy(y) + 4} fontSize={11} textAnchor="end" className={tickClass}>
            {fmtY(y, metric)}
          </text>
        </g>
      ))}

      {/* major x-tick labels */}
      {xMajor.map((x, i) => (
        <g key={`x${i}`}>
          <line x1={sx(x)} y1={H - PAD_B} x2={sx(x)} y2={H - PAD_B + 5} className="stroke-border-strong" />
          <text x={sx(x)} y={H - PAD_B + 17} fontSize={11} textAnchor="middle" className={tickClass}>
            {fmtX(x, parameter, series.xLog)}
          </text>
        </g>
      ))}

      {/* outer axes */}
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} className="stroke-border-strong" />
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} className="stroke-border-strong" />

      {/* axis titles */}
      <text x={xTitleX} y={xTitleY} textAnchor="middle" fontSize={12} className={titleClass}>
        {xAxisLabel(parameter)}
      </text>
      <text
        transform={`rotate(-90, ${yTitleX}, ${yTitleY})`}
        x={yTitleX} y={yTitleY} textAnchor="middle" fontSize={12} className={titleClass}
      >
        {METRIC_AXIS_LABEL[metric]}
      </text>

      {/* data line + points, themed via currentColor */}
      <g className="text-accent-strong">
        <path d={path} fill="none" stroke="currentColor" strokeWidth={1.75}
          strokeLinejoin="round" strokeLinecap="round" />
        {series.x.map((x, i) => (
          <circle key={i} cx={sx(x)} cy={sy(series.y[i])} r={1.75} fill="currentColor" />
        ))}
      </g>

      {/* hover crosshair + focused point */}
      {hover && (
        <g className="text-accent-strong" pointerEvents="none">
          <line x1={hover.sx} y1={PAD_T} x2={hover.sx} y2={H - PAD_B}
            stroke="currentColor" strokeWidth={1} strokeDasharray="2 4" opacity={0.75} />
          <circle cx={hover.sx} cy={hover.sy} r={3.5} fill="currentColor" stroke="#0a0e16" strokeWidth={1.5} />
        </g>
      )}

      {/* hover readout box */}
      {hover && (
        <g pointerEvents="none" transform={`translate(${readoutX} ${readoutY})`}>
          <rect width={readoutW} height={readoutH} rx={3}
            className="fill-surface-raised stroke-border-strong" strokeWidth={1} opacity={0.96} />
          <text x={8} y={15} fontSize={11} className="fill-slate-300 font-mono">
            <tspan className="fill-slate-500">x </tspan>
            {fmtReadX(series.x[hover.i], parameter)}
          </text>
          <text x={8} y={30} fontSize={11} className="fill-slate-100 font-mono">
            <tspan className="fill-slate-500">y </tspan>
            {fmtReadY(series.y[hover.i], metric)}
          </text>
        </g>
      )}

      {/* invisible capture rect — top of stack so hover works anywhere in plot area */}
      <rect
        x={PAD_L} y={PAD_T} width={W - PAD_L - PAD_R} height={H - PAD_T - PAD_B}
        fill="transparent" pointerEvents="all"
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}
      />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"
        stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
