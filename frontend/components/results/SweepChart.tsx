"use client";

import { useMemo, useState } from "react";
import { runSweep, type SweepPoint } from "@/lib/api";
import { useGuiStore } from "@/lib/store";

type Metric = "z0" | "eps_eff" | "dielectric_loss_db_per_in";

const METRIC_LABEL: Record<Metric, string> = {
  z0: "Z₀ (Ω)",
  eps_eff: "εr_eff",
  dielectric_loss_db_per_in: "α_d (dB/in)",
};

/**
 * Hand-rolled SVG line chart. No charting-lib dep.
 *
 * Plots one of (z0 / eps_eff / dielectric_loss_db_per_in) on y vs the
 * sweep parameter on x. Frequency sweeps use log-x; geometry sweeps use
 * linear-x. Hover shows a crosshair with point values.
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
      // Log-spaced for frequency, linear for everything else.
      const values: number[] = [];
      if (parameter === "frequency") {
        const lLo = Math.log10(lo);
        const lHi = Math.log10(hi);
        for (let i = 0; i < n; i++) {
          values.push(Math.pow(10, lLo + (i * (lHi - lLo)) / (n - 1)));
        }
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
      const ts = resp.touchstone as
        | { filename: string; content: string }
        | undefined;
      if (!ts) throw new Error("backend returned no touchstone payload");
      // Trigger a browser download from the inlined .s2p text.
      const content: string = ts.content;
      const blob = new Blob([content], { type: "text/plain" });
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

  const series = useMemo(() => buildSeries(sweepResults, sweepConfig?.parameter, metric), [
    sweepResults,
    sweepConfig?.parameter,
    metric,
  ]);

  const canExport =
    sweepConfig?.parameter === "frequency" && (sweepResults?.length ?? 0) >= 2;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Sweep</div>
        <button
          onClick={exportTouchstone}
          disabled={!canExport || busy}
          title={
            canExport
              ? "Re-run sweep with Touchstone export and download .s2p"
              : "Run a frequency sweep first"
          }
          className="text-xs bg-cyan-700 hover:bg-cyan-600 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded px-2 py-0.5"
        >
          ↓ .s2p
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <label className="block">
          <span className="block text-slate-400 mb-1">Parameter</span>
          <select
            value={parameter}
            onChange={(e) => setParameter(e.target.value)}
            className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1 text-slate-100"
          >
            <option value="frequency">frequency</option>
            <option value="W">W</option>
            <option value="H">H</option>
            <option value="T">T</option>
            <option value="er">er</option>
          </select>
        </label>
        <label className="block">
          <span className="block text-slate-400 mb-1">Y-axis</span>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as Metric)}
            className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1 text-slate-100"
          >
            <option value="z0">{METRIC_LABEL.z0}</option>
            <option value="eps_eff">{METRIC_LABEL.eps_eff}</option>
            <option value="dielectric_loss_db_per_in">{METRIC_LABEL.dielectric_loss_db_per_in}</option>
          </select>
        </label>
        <label className="block">
          <span className="block text-slate-400 mb-1">Start</span>
          <input
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1 text-slate-100 font-mono"
          />
        </label>
        <label className="block">
          <span className="block text-slate-400 mb-1">Stop</span>
          <input
            value={stop}
            onChange={(e) => setStop(e.target.value)}
            className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1 text-slate-100 font-mono"
          />
        </label>
        <label className="block">
          <span className="block text-slate-400 mb-1">Points</span>
          <input
            type="number"
            value={n}
            onChange={(e) => setN(Math.max(2, Math.min(401, parseInt(e.target.value) || 31)))}
            className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1 text-slate-100 font-mono"
          />
        </label>
        <button
          onClick={run}
          disabled={!geometry || busy}
          className="self-end bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded px-3 py-1.5 text-xs font-medium"
        >
          {busy ? "Sweeping…" : "Run sweep"}
        </button>
      </div>

      {err && (
        <div className="bg-rose-950/40 border border-rose-800 rounded p-2 text-xs text-rose-300">
          {err}
        </div>
      )}

      {series && <ChartSVG series={series} metric={metric} parameter={sweepConfig?.parameter ?? parameter} />}

      {!series && !busy && (
        <div className="text-[11px] text-slate-500 italic">
          Configure a geometry on the left, then run a sweep.
        </div>
      )}
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

function ChartSVG({
  series,
  metric,
  parameter,
}: {
  series: { x: number[]; y: number[]; xLog: boolean };
  metric: Metric;
  parameter: string;
}) {
  const W = 460;
  const H = 240;
  const PAD_L = 56;
  const PAD_R = 14;
  const PAD_T = 12;
  const PAD_B = 32;

  const xMin = Math.min(...series.x);
  const xMax = Math.max(...series.x);
  const yMin = Math.min(...series.y);
  const yMax = Math.max(...series.y);
  const yPad = (yMax - yMin) * 0.08 || Math.abs(yMax) * 0.05 || 1;
  const yLo = yMin - yPad;
  const yHi = yMax + yPad;

  function sx(x: number): number {
    if (series.xLog) {
      const t = (Math.log10(x) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin));
      return PAD_L + t * (W - PAD_L - PAD_R);
    }
    return PAD_L + ((x - xMin) / (xMax - xMin)) * (W - PAD_L - PAD_R);
  }
  function sy(y: number): number {
    return H - PAD_B - ((y - yLo) / (yHi - yLo)) * (H - PAD_T - PAD_B);
  }

  const path = series.x
    .map((x, i) => `${i === 0 ? "M" : "L"} ${sx(x).toFixed(2)} ${sy(series.y[i]).toFixed(2)}`)
    .join(" ");

  // Tick marks: 5 evenly spaced y-ticks; for x, use decade ticks (log) or 5 even (linear).
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => yLo + t * (yHi - yLo));
  const xTicks: number[] = series.xLog
    ? logDecades(xMin, xMax)
    : [0, 0.25, 0.5, 0.75, 1].map((t) => xMin + t * (xMax - xMin));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto bg-navy-950 border border-navy-800 rounded">
      {/* axes */}
      <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="#475569" />
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="#475569" />
      {/* grid + y ticks */}
      {yTicks.map((y, i) => (
        <g key={`y${i}`}>
          <line
            x1={PAD_L}
            y1={sy(y)}
            x2={W - PAD_R}
            y2={sy(y)}
            stroke="#1e293b"
            strokeDasharray="2,3"
          />
          <text
            x={PAD_L - 6}
            y={sy(y) + 3}
            fontSize={9}
            textAnchor="end"
            fill="#94a3b8"
            fontFamily="ui-monospace, monospace"
          >
            {fmtY(y, metric)}
          </text>
        </g>
      ))}
      {/* x ticks */}
      {xTicks.map((x, i) => (
        <g key={`x${i}`}>
          <line x1={sx(x)} y1={H - PAD_B} x2={sx(x)} y2={H - PAD_B + 4} stroke="#475569" />
          <text
            x={sx(x)}
            y={H - PAD_B + 14}
            fontSize={9}
            textAnchor="middle"
            fill="#94a3b8"
            fontFamily="ui-monospace, monospace"
          >
            {fmtX(x, parameter, series.xLog)}
          </text>
        </g>
      ))}
      {/* line */}
      <path d={path} fill="none" stroke="#06b6d4" strokeWidth={1.5} />
      {/* points */}
      {series.x.map((x, i) => (
        <circle key={i} cx={sx(x)} cy={sy(series.y[i])} r={1.5} fill="#22d3ee" />
      ))}
      {/* axis labels */}
      <text
        x={W / 2}
        y={H - 4}
        fontSize={10}
        textAnchor="middle"
        fill="#94a3b8"
        fontFamily="ui-monospace, monospace"
      >
        {parameter}
      </text>
      <text
        x={12}
        y={H / 2}
        fontSize={10}
        fill="#94a3b8"
        textAnchor="middle"
        transform={`rotate(-90, 12, ${H / 2})`}
        fontFamily="ui-monospace, monospace"
      >
        {METRIC_LABEL[metric]}
      </text>
    </svg>
  );
}

function logDecades(lo: number, hi: number): number[] {
  const lLo = Math.ceil(Math.log10(lo));
  const lHi = Math.floor(Math.log10(hi));
  const out: number[] = [];
  for (let l = lLo; l <= lHi; l++) out.push(Math.pow(10, l));
  if (out.length === 0 || out[0] !== lo) out.unshift(lo);
  if (out[out.length - 1] !== hi) out.push(hi);
  return out;
}

function fmtX(x: number, parameter: string, xLog: boolean): string {
  if (parameter === "frequency") {
    if (x >= 1e9) return `${(x / 1e9).toFixed(x >= 10e9 ? 0 : 1)}G`;
    if (x >= 1e6) return `${(x / 1e6).toFixed(x >= 10e6 ? 0 : 1)}M`;
    if (x >= 1e3) return `${(x / 1e3).toFixed(0)}k`;
    return x.toFixed(0);
  }
  if (xLog) return x.toExponential(0);
  if (x >= 100) return x.toFixed(0);
  if (x >= 1) return x.toFixed(2);
  return x.toExponential(1);
}

function fmtY(y: number, metric: Metric): string {
  if (metric === "z0") return y.toFixed(1);
  if (metric === "dielectric_loss_db_per_in") return y.toFixed(3);
  return y.toFixed(3);
}
