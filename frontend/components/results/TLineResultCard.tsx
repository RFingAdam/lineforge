"use client";

import { Stat } from "./Stat";

const C0 = 299_792_458;

export function TLineResultCard({ result }: { result: Record<string, unknown> }) {
  const z0 = num(result, "z0");
  const epsEff = num(result, "eps_eff");
  const vp = num(result, "vp");
  const td = num(result, "td_per_inch");
  const L = num(result, "L_per_m");
  const C = num(result, "C_per_m");
  const ad = num(result, "dielectric_loss_db_per_in");
  const ac = num(result, "conductor_loss_db_per_in");
  const method = result.method as string | undefined;

  return (
    <div className="space-y-3">
      {z0 !== null && (
        <Stat
          label="Z₀"
          value={z0.toFixed(3)}
          unit="Ω"
          emphasis
          color="text-emerald-300"
        />
      )}
      <div className="grid grid-cols-2 gap-3">
        {epsEff !== null && <Stat label="εr_eff" value={epsEff.toFixed(4)} />}
        {vp !== null && (
          <Stat
            label="vp"
            value={(vp / 1e8).toFixed(3)}
            unit={`× 10⁸ m/s (${(vp / C0).toFixed(3)} c)`}
          />
        )}
        {td !== null && <Stat label="td/in" value={(td * 1e12).toFixed(2)} unit="ps/in" />}
        {L !== null && <Stat label="L" value={(L * 1e9).toFixed(1)} unit="nH/m" />}
        {C !== null && <Stat label="C" value={(C * 1e12).toFixed(1)} unit="pF/m" />}
        {ad !== null && (
          <Stat label="α_d" value={ad.toFixed(4)} unit="dB/in" color="text-amber-300" />
        )}
        {ac !== null && (
          <Stat label="α_c" value={ac.toFixed(4)} unit="dB/in" color="text-amber-300" />
        )}
      </div>
      {method && <div className="text-xs text-slate-500">method: {method}</div>}
    </div>
  );
}

function num(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}
