"use client";

import { useEffect, useState } from "react";

type Laminate = {
  name: string;
  er: number;
  tan_delta: number;
  er_freq?: Record<string, number> | null;
  tan_freq?: Record<string, number> | null;
};

/**
 * Combobox for picking a laminate from atlc3.materials.packs.pcb_extended.
 * On selection, calls ``onPick(er, tan_delta)`` so the parent can write
 * those values into the geometry form. Manual override is preserved by
 * clearing the selection if the parent's er/tan_delta later differ from
 * any catalog entry.
 */
export function MaterialPicker({
  onPick,
  currentEr,
  currentTanDelta,
}: {
  onPick: (er: number, tanDelta: number, name: string) => void;
  currentEr?: number;
  currentTanDelta?: number;
}) {
  const [laminates, setLaminates] = useState<Laminate[]>([]);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    fetch("/api/materials/laminates")
      .then((r) => r.json())
      .then((body: { laminates: Laminate[] }) => setLaminates(body.laminates))
      .catch(() => setLaminates([]));
  }, []);

  // Clear the dropdown selection if the user manually edits εr/tan_δ to
  // values that don't match the selected laminate.
  useEffect(() => {
    if (!selected) return;
    const lam = laminates.find((l) => l.name === selected);
    if (!lam) return;
    if (
      currentEr !== undefined &&
      currentTanDelta !== undefined &&
      (Math.abs(lam.er - currentEr) > 1e-6 ||
        Math.abs(lam.tan_delta - currentTanDelta) > 1e-9)
    ) {
      setSelected("");
    }
  }, [currentEr, currentTanDelta, laminates, selected]);

  return (
    <label className="block">
      <span className="block text-xs text-slate-400 mb-1">Material (catalog)</span>
      <select
        value={selected}
        onChange={(e) => {
          const name = e.target.value;
          setSelected(name);
          if (!name) return;
          const lam = laminates.find((l) => l.name === name);
          if (lam) onPick(lam.er, lam.tan_delta, lam.name);
        }}
        className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1.5 text-slate-100 text-sm"
      >
        <option value="">(custom — type εr / tan_δ below)</option>
        {laminates.map((l) => (
          <option
            key={l.name}
            value={l.name}
            title={
              l.er_freq
                ? `Multi-frequency: ${Object.keys(l.er_freq).length} points`
                : `εr=${l.er}, tan_δ=${l.tan_delta}`
            }
          >
            {l.name} — εr {l.er.toFixed(2)}{l.tan_delta > 0 ? `, tan_δ ${l.tan_delta}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
