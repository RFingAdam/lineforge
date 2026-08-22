/**
 * Pure helpers extracted from SweepChart.tsx to keep the component file
 * focused on JSX. None of these reference React state. They're tick
 * generators and number formatters used by the SVG renderer.
 */

export type Metric = "z0" | "eps_eff" | "dielectric_loss_db_per_in";

export const METRIC_LABEL: Record<Metric, string> = {
  z0: "Z₀ (Ω)",
  eps_eff: "εr_eff",
  dielectric_loss_db_per_in: "α_d (dB/in)",
};

// Distinct from METRIC_LABEL: this flavour goes on the rotated y-axis
// and the chart header chip ("[Ω]" reads like a unit annotation in a
// scientific paper; "(Ω)" reads more like a UI affordance).
export const METRIC_AXIS_LABEL: Record<Metric, string> = {
  z0: "Z₀ [Ω]",
  eps_eff: "εᵣ_eff",
  dielectric_loss_db_per_in: "α_d [dB/in]",
};

export function xAxisLabel(parameter: string): string {
  if (parameter === "frequency") return "Frequency [Hz]";
  if (parameter === "W") return "Trace width W [mil]";
  if (parameter === "H") return "Dielectric height H [mil]";
  if (parameter === "T") return "Conductor thickness T [oz]";
  if (parameter === "er") return "Dielectric εᵣ";
  return parameter;
}

export function logDecades(lo: number, hi: number): number[] {
  const lLo = Math.ceil(Math.log10(lo));
  const lHi = Math.floor(Math.log10(hi));
  const out: number[] = [];
  for (let l = lLo; l <= lHi; l++) out.push(Math.pow(10, l));
  if (out.length === 0 || out[0] !== lo) out.unshift(lo);
  if (out[out.length - 1] !== hi) out.push(hi);
  return out;
}

/** Canonical 2..9 intra-decade ticks across [lo, hi]. */
export function logMinors(lo: number, hi: number): number[] {
  const lLo = Math.floor(Math.log10(lo));
  const lHi = Math.ceil(Math.log10(hi));
  const out: number[] = [];
  for (let l = lLo; l <= lHi; l++) {
    for (let k = 2; k <= 9; k++) {
      const v = k * Math.pow(10, l);
      if (v > lo && v < hi) out.push(v);
    }
  }
  return out;
}

/** 3 evenly-spaced minor ticks between each pair of majors. */
export function linearMinors(major: number[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < major.length - 1; i++) {
    const a = major[i];
    const b = major[i + 1];
    for (let k = 1; k < 4; k++) out.push(a + ((b - a) * k) / 4);
  }
  return out;
}

export function fmtX(x: number, parameter: string, xLog: boolean): string {
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

export function fmtY(y: number, metric: Metric): string {
  if (metric === "z0") return y.toFixed(1);
  return y.toFixed(3);
}

/** Hover-readout flavour of fmtX: preserves SI prefix but appends units. */
export function fmtReadX(x: number, parameter: string): string {
  if (parameter === "frequency") {
    if (x >= 1e9) return `${(x / 1e9).toFixed(3)} GHz`;
    if (x >= 1e6) return `${(x / 1e6).toFixed(3)} MHz`;
    if (x >= 1e3) return `${(x / 1e3).toFixed(3)} kHz`;
    return `${x.toFixed(1)} Hz`;
  }
  if (Math.abs(x) >= 100 || Math.abs(x) < 0.01) return x.toExponential(3);
  return x.toFixed(4);
}

export function fmtReadY(y: number, metric: Metric): string {
  if (metric === "z0") return `${y.toFixed(2)} Ω`;
  if (metric === "dielectric_loss_db_per_in") return `${y.toFixed(4)} dB/in`;
  return y.toFixed(4);
}
