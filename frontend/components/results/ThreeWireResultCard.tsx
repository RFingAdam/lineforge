"use client";

import { Stat } from "./Stat";

export function ThreeWireResultCard({ result }: { result: Record<string, unknown> }) {
  const zr = num(result, "zo_r");
  const zg = num(result, "zo_g");
  const zb = num(result, "zo_b");
  const zo = num(result, "z_odd");
  const ze = num(result, "z_even");
  const ignd = num(result, "ignd_ratio") ?? 0;
  const radiating = ignd > 0.04;
  const method = result.method as string | undefined;

  return (
    <div className="space-y-3">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        3-wire Y-decomposition
      </div>
      <div className="grid grid-cols-3 gap-3">
        {zr !== null && (
          <Stat label="Z₀_R" value={zr.toFixed(2)} unit="Ω" color="text-rose-400" />
        )}
        {zg !== null && (
          <Stat label="Z₀_G" value={zg.toFixed(2)} unit="Ω" color="text-emerald-400" />
        )}
        {zb !== null && (
          <Stat label="Z₀_B" value={zb.toFixed(2)} unit="Ω" color="text-blue-400" />
        )}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {zo !== null && (
          <Stat label="Z_odd" value={zo.toFixed(2)} unit="Ω" color="text-cyan-300" />
        )}
        {ze !== null && (
          <Stat label="Z_even" value={ze.toFixed(2)} unit="Ω" color="text-cyan-300" />
        )}
      </div>
      <Stat
        label="|I_gnd / I_sig|"
        value={(ignd * 100).toFixed(2)}
        unit="%"
        color={radiating ? "text-rose-400" : "text-slate-300"}
      />
      {radiating && (
        <div className="bg-rose-950/40 border border-rose-800 rounded p-2 text-xs text-rose-300">
          ⚠ Net ground current &gt; 4% — geometry is radiating; reported Z₀
          values are approximate.
        </div>
      )}
      <div className="text-xs text-slate-500 leading-relaxed">
        Y-decomposition: Z₀_R / Z₀_G / Z₀_B are the three Y-leg impedances.
        Z_odd = 2·Z₀_R; Z_even = Z₀_R / 2 + Z₀_B.
      </div>
      {method && <div className="text-xs text-slate-500">method: {method}</div>}
    </div>
  );
}

function num(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}
