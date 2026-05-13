"use client";

import { Section } from "../ui";
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
    <div className="space-y-4">
      {zd !== null && (
        <Stat
          label="Z_diff"
          value={zd.toFixed(2)}
          unit="Ω"
          hero
          tone="accent"
          hint="Differential-mode characteristic impedance — 2·Z_odd"
        />
      )}

      <Section title="Odd-mode">
        <div className="grid grid-cols-2 gap-2.5">
          {zo !== null && <Stat label="Z_odd" value={zo.toFixed(2)} unit="Ω" />}
          {epsOdd !== null && <Stat label="ε_eff_odd" value={epsOdd.toFixed(4)} />}
        </div>
      </Section>

      <Section title="Even-mode">
        <div className="grid grid-cols-2 gap-2.5">
          {ze !== null && <Stat label="Z_even" value={ze.toFixed(2)} unit="Ω" />}
          {zc !== null && (
            <Stat
              label="Z_common"
              value={zc.toFixed(2)}
              unit="Ω"
              tone="info"
              hint="Common-mode impedance — Z_even / 2"
            />
          )}
          {epsEven !== null && <Stat label="ε_eff_even" value={epsEven.toFixed(4)} />}
        </div>
      </Section>

      <p className="text-[11px] text-slate-500 leading-relaxed">
        Z_diff = 2·Z_odd governs your fab&apos;s controlled-impedance spec;
        Z_common = Z_even / 2 indicates return-path quality.
      </p>

      {method && (
        <div className="text-[11px] text-slate-500 font-mono">method: {method}</div>
      )}
    </div>
  );
}

function num(obj: Record<string, unknown>, key: string): number | null {
  const v = obj[key];
  return typeof v === "number" ? v : null;
}
