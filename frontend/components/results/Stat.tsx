"use client";

/** A single stat card: label above, big value below. Used to compose the
 * various result-kind sub-panels with consistent visual weight. */
export function Stat({
  label,
  value,
  unit,
  emphasis = false,
  color,
}: {
  label: string;
  value: string;
  unit?: string;
  emphasis?: boolean;
  color?: string;
}) {
  return (
    <div className="bg-navy-900 border border-navy-800 rounded p-3">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
      <div
        className={
          (emphasis ? "text-2xl " : "text-base ") +
          "font-mono mt-0.5 " +
          (color ?? "text-slate-100")
        }
      >
        {value}
        {unit && <span className="text-xs text-slate-500 ml-1">{unit}</span>}
      </div>
    </div>
  );
}
