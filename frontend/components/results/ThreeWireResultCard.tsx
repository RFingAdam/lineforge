"use client";

import { Card, Section } from "../ui";
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

  const heroLabel = zr !== null ? "Z₀_R" : zg !== null ? "Z₀_G" : "Z₀_B";
  const heroValue = zr ?? zg ?? zb;

  return (
    <div className="space-y-4">
      {heroValue !== null && (
        <Stat label={heroLabel} value={heroValue.toFixed(2)} unit="Ω" hero tone="accent" />
      )}

      <Section title="Y-decomposition (per leg)">
        <div className="grid grid-cols-3 gap-2.5">
          {zr !== null && <Stat label="Z₀_R" value={zr.toFixed(2)} unit="Ω" tone="danger" />}
          {zg !== null && (
            <Stat label="Z₀_G" value={zg.toFixed(2)} unit="Ω" tone="success" />
          )}
          {zb !== null && <Stat label="Z₀_B" value={zb.toFixed(2)} unit="Ω" tone="info" />}
        </div>
      </Section>

      <Section title="Mode impedances">
        <div className="grid grid-cols-2 gap-2.5">
          {zo !== null && <Stat label="Z_odd" value={zo.toFixed(2)} unit="Ω" />}
          {ze !== null && <Stat label="Z_even" value={ze.toFixed(2)} unit="Ω" />}
        </div>
      </Section>

      <Section title="Return-path quality">
        <Stat
          label="|I_gnd / I_sig|"
          value={(ignd * 100).toFixed(2)}
          unit="%"
          tone={radiating ? "danger" : "default"}
          hint="Net ground current as a fraction of signal current"
        />
        {radiating && (
          <Card
            tone="raised"
            role="alert"
            className="border-danger/60 bg-danger/10 mt-2 text-[11px] text-danger"
          >
            ⚠ Net ground current &gt; 4% — geometry is radiating; reported Z₀ values are
            approximate.
          </Card>
        )}
      </Section>

      <p className="text-[11px] text-slate-500 leading-relaxed">
        Y-decomposition: Z₀_R / Z₀_G / Z₀_B are the three Y-leg impedances. Z_odd =
        2·Z₀_R; Z_even = Z₀_R / 2 + Z₀_B.
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
