"use client";

import { Section } from "../ui";
import { Stat } from "./Stat";

const C0 = 299_792_458;

export function TLineResultCard({ result }: { result: Record<string, unknown> }) {
  const z0 = num(result, "z0");
  const epsEff = num(result, "eps_eff");
  const vp = num(result, "vp");
  const td = num(result, "td_per_inch");
  const L = num(result, "L_per_m");
  const C = num(result, "C_per_m");
  const Rs = num(result, "Rs_per_m");
  const Gp = num(result, "Gp_per_m");
  const ad = num(result, "dielectric_loss_db_per_in");
  const ac = num(result, "conductor_loss_db_per_in");
  const method = result.method as string | undefined;

  const aTotal = ad !== null && ac !== null ? ad + ac : null;

  const hasPropagation = epsEff !== null || vp !== null || td !== null;
  const hasDistributed = L !== null || C !== null || Rs !== null || Gp !== null;
  const hasLoss = ad !== null || ac !== null || aTotal !== null;

  return (
    <div className="space-y-4">
      {z0 !== null && (
        <Stat label="Z₀" value={z0.toFixed(3)} unit="Ω" hero tone="accent" />
      )}

      {hasPropagation && (
        <Section title="Impedance & Propagation">
          <div className="grid grid-cols-2 gap-2.5">
            {epsEff !== null && <Stat label="ε_eff" value={epsEff.toFixed(4)} />}
            {vp !== null && (
              <Stat
                label="v_p"
                value={(vp / 1e8).toFixed(3)}
                unit="× 10⁸ m/s"
                hint={`${(vp / C0).toFixed(3)} c`}
              />
            )}
            {td !== null && (
              <Stat label="t_d" value={(td * 1e12).toFixed(2)} unit="ps/in" />
            )}
          </div>
        </Section>
      )}

      {hasDistributed && (
        <Section title="Distributed parameters">
          <div className="grid grid-cols-2 gap-2.5">
            {L !== null && <Stat label="L" value={(L * 1e9).toFixed(1)} unit="nH/m" />}
            {C !== null && <Stat label="C" value={(C * 1e12).toFixed(1)} unit="pF/m" />}
            {Rs !== null && (
              <Stat label="R_s" value={Rs.toFixed(3)} unit="Ω/m" tone="info" />
            )}
            {Gp !== null && (
              <Stat label="G_p" value={Gp.toExponential(2)} unit="S/m" tone="info" />
            )}
          </div>
        </Section>
      )}

      {hasLoss && (
        <Section title="Loss">
          <div className="grid grid-cols-2 gap-2.5">
            {ac !== null && (
              <Stat label="α_c" value={ac.toFixed(4)} unit="dB/in" tone="warn" />
            )}
            {ad !== null && (
              <Stat label="α_d" value={ad.toFixed(4)} unit="dB/in" tone="warn" />
            )}
            {aTotal !== null && (
              <Stat
                label="α_total"
                value={aTotal.toFixed(4)}
                unit="dB/in"
                tone="warn"
                hint="α_c + α_d"
              />
            )}
          </div>
        </Section>
      )}

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
