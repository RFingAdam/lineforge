"use client";

import { Stat } from "./Stat";

export function DiffResultCard({ result }: { result: Record<string, unknown> }) {
  const zo = num(result, "z_odd");
  const ze = num(result, "z_even");
  const zd = num(result, "z_diff");
  const zc = num(result, "z_common");
  const epsOdd = num(result, "eps_eff_odd");
  const epsEven = num(result, "eps_eff_even");
  const method = result.method as string | undefined;

  return (
    <div className="space-y-3">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        Differential pair
      </div>
      <div className="grid grid-cols-2 gap-3">
        {zd !== null && (
          <Stat
            label="Z_diff"
            value={zd.toFixed(2)}
            unit="Ω"
            emphasis
            color="text-emerald-300"
          />
        )}
        {zc !== null && (
          <Stat label="Z_common" value={zc.toFixed(2)} unit="Ω" color="text-cyan-300" />
        )}
        {zo !== null && <Stat label="Z_odd" value={zo.toFixed(2)} unit="Ω" />}
        {ze !== null && <Stat label="Z_even" value={ze.toFixed(2)} unit="Ω" />}
        {epsOdd !== null && <Stat label="εeff (odd)" value={epsOdd.toFixed(4)} />}
        {epsEven !== null && <Stat label="εeff (even)" value={epsEven.toFixed(4)} />}
      </div>
      <div className="text-xs text-slate-500 leading-relaxed">
        Z_diff = 2·Z_odd, Z_common = Z_even / 2. Use Z_diff to design pair
        impedance against your fab&apos;s controlled-impedance spec; Z_common to
        check return-path quality.
      </div>
      {method && <div className="text-xs text-slate-500">method: {method}</div>}
    </div>
  );
}

function num(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}
