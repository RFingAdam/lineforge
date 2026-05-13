"use client";

import { Fragment, type ReactNode } from "react";
import { SkeletonRow } from "../Skeleton";

/**
 * Single-metric card primitive used by every results view.
 *
 * Visual hierarchy is controlled by two orthogonal props:
 *   - `hero` flips to the larger "headline" variant (2× height, accent left
 *     border, oversized mono numerals). Use this for the dominant value of a
 *     result group — Z₀, Z_diff, etc.
 *   - `tone` tints the card to convey semantic meaning. `default` stays neutral
 *     `surface-raised`; status tones layer a faint colored fill and border.
 *
 * `label` accepts plain strings (which run through {@link MathLabel} so common
 * notations like `Z₀`, `Z_diff`, `ε_eff`, `α_c` render with proper subscripts
 * and Greek letters), but callers that need a richer label — e.g. a label with
 * an inline help icon — can pass `labelNode` instead.
 *
 * `delta` renders a small inline pill below the value; `sparkline` slots a
 * caller-provided ReactNode (usually a tiny inline SVG) to the right of the
 * hero numeral.
 */

export type StatTone = "default" | "accent" | "success" | "warn" | "danger" | "info";

interface DeltaPill {
  value: number;
  unit?: string;
  tone?: StatTone;
}

interface StatProps {
  label: string;
  labelNode?: ReactNode;
  value: number | string;
  unit?: string;
  tone?: StatTone;
  hero?: boolean;
  hint?: string;
  delta?: DeltaPill;
  loading?: boolean;
  sparkline?: ReactNode;
}

const TONE_BG: Record<StatTone, string> = {
  default: "surface-raised",
  accent: "bg-accent/5 border border-accent/40 rounded-md shadow-card",
  success: "bg-success/5 border border-success/40 rounded-md shadow-card",
  warn: "bg-warn/5 border border-warn/40 rounded-md shadow-card",
  danger: "bg-danger/5 border border-danger/40 rounded-md shadow-card",
  info: "bg-info/5 border border-info/40 rounded-md shadow-card",
};

const TONE_VALUE: Record<StatTone, string> = {
  default: "text-slate-100",
  accent: "text-accent-strong",
  success: "text-success",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
};

const TONE_HERO_BORDER: Record<StatTone, string> = {
  default: "border-border-strong",
  accent: "border-accent",
  success: "border-success",
  warn: "border-warn",
  danger: "border-danger",
  info: "border-info",
};

const TONE_PILL: Record<StatTone, string> = {
  default: "bg-surface-overlay text-slate-300 border-border-strong",
  accent: "bg-accent/10 text-accent-strong border-accent/40",
  success: "bg-success/10 text-success border-success/40",
  warn: "bg-warn/10 text-warn border-warn/40",
  danger: "bg-danger/10 text-danger border-danger/40",
  info: "bg-info/10 text-info border-info/40",
};

export function Stat({
  label,
  labelNode,
  value,
  unit,
  tone = "default",
  hero = false,
  hint,
  delta,
  loading = false,
  sparkline,
}: StatProps) {
  const containerCls = hero
    ? `surface rounded-sm border-l-4 ${TONE_HERO_BORDER[tone]} px-4 py-4`
    : `${TONE_BG[tone]} px-3 py-2`;

  const labelCls = hero
    ? "text-xs uppercase tracking-wider text-slate-400 font-display"
    : "text-[11px] uppercase tracking-wider text-slate-400 font-display";

  const valueCls = hero
    ? `font-mono text-3xl tabular-nums leading-none ${TONE_VALUE[tone]}`
    : `font-mono text-lg tabular-nums leading-tight ${TONE_VALUE[tone]}`;

  const unitCls = hero
    ? "text-base text-slate-400 ml-1.5 font-display"
    : "text-xs text-slate-500 ml-1 font-display";

  return (
    <div className={containerCls} title={hint} aria-label={label} role="group">
      <div className={labelCls}>{labelNode ?? <MathLabel>{label}</MathLabel>}</div>
      <div className={hero ? "mt-2 flex items-end justify-between gap-3" : "mt-1"}>
        <div>
          {loading ? (
            <SkeletonRow className={hero ? "h-8 w-32" : "h-5 w-20"} />
          ) : (
            <span className={valueCls}>
              {value}
              {unit && <span className={unitCls}>{unit}</span>}
            </span>
          )}
          {delta && !loading && (
            <div className="mt-1.5">
              <DeltaIndicator delta={delta} />
            </div>
          )}
        </div>
        {hero && sparkline && (
          <div className="shrink-0 opacity-80" aria-hidden="true">
            {sparkline}
          </div>
        )}
      </div>
    </div>
  );
}

function DeltaIndicator({ delta }: { delta: DeltaPill }) {
  const tone = delta.tone ?? "default";
  const sign = delta.value > 0 ? "↑" : delta.value < 0 ? "↓" : "→";
  const abs = Math.abs(delta.value);
  const formatted = abs >= 10 ? abs.toFixed(1) : abs >= 1 ? abs.toFixed(2) : abs.toFixed(3);
  const prefix = delta.value > 0 ? "+" : delta.value < 0 ? "−" : "";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-xs border px-1.5 py-0.5
                  text-[10px] font-mono tabular-nums ${TONE_PILL[tone]}`}
    >
      <span aria-hidden="true">{sign}</span>
      <span>
        {prefix}
        {formatted}
        {delta.unit && (
          <span className="ml-0.5 text-slate-400 font-display">{delta.unit}</span>
        )}
      </span>
    </span>
  );
}

/**
 * Renders math-y labels with proper subscripts and Greek letters.
 *
 * Supported notations:
 *   - "X₀", "X_diff", "X_eff"     → subscript after underscore (or trailing 0/1/2)
 *   - "ε", "α", "μ", "σ", "Ω"     → pass through (already Unicode glyphs)
 *   - bare strings like "v_p"     → renders "v" with "p" subscripted
 */
export function MathLabel({ children }: { children: string }) {
  const tokens = children.split(/(_[A-Za-z0-9]+|[₀-₉]+)/g);
  return (
    <>
      {tokens.map((tok, i) => {
        if (!tok) return null;
        if (tok.startsWith("_")) {
          return (
            <sub key={i} className="text-[0.75em] font-normal align-baseline">
              {tok.slice(1)}
            </sub>
          );
        }
        return <Fragment key={i}>{tok}</Fragment>;
      })}
    </>
  );
}
