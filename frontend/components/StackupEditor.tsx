"use client";

import { useState } from "react";
import { useGuiStore } from "@/lib/store";
import { formatMeters } from "@/lib/units";

type Layer = {
  h: string; // user-typed length (e.g. "5.3mil")
  er: string; // user-typed float string
  tan_delta: string;
  name: string;
};

const EMPTY_LAYER: Layer = { h: "", er: "", tan_delta: "0", name: "" };

const PRESET_L3_SIG1: Layer[] = [
  { h: "5.3mil", er: "3.7", tan_delta: "0.020", name: "Prepreg" },
  { h: "1.4mil", er: "3.7", tan_delta: "0.020", name: "L4 voided" },
  { h: "3.5mil", er: "4.2", tan_delta: "0.020", name: "Core" },
];

/**
 * Modal-style stackup editor for stack_above / stack_below. Two parallel
 * tables; each row is one DielectricLayer. On Save, we POST to
 * /api/materials/series_reduce per side and write the reduced (h, εr,
 * tan_δ) values back to the geometry form's H1/H2 + er_above/er_below +
 * tan_delta_above/tan_delta_below.
 */
export function StackupEditor({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const geometry = useGuiStore((s) => s.geometry);
  const setGeometry = useGuiStore((s) => s.setGeometry);
  const unit = useGuiStore((s) => s.unit);

  const [above, setAbove] = useState<Layer[]>([{ ...EMPTY_LAYER }]);
  const [below, setBelow] = useState<Layer[]>(PRESET_L3_SIG1.map((l) => ({ ...l })));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!open) return null;

  function updateLayer(side: "above" | "below", idx: number, patch: Partial<Layer>) {
    const setter = side === "above" ? setAbove : setBelow;
    setter((s) => s.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }
  function addLayer(side: "above" | "below") {
    const setter = side === "above" ? setAbove : setBelow;
    setter((s) => [...s, { ...EMPTY_LAYER }]);
  }
  function removeLayer(side: "above" | "below", idx: number) {
    const setter = side === "above" ? setAbove : setBelow;
    setter((s) => s.filter((_, i) => i !== idx));
  }

  async function reduceSide(side: Layer[]): Promise<{ h: number; er: number; tan: number } | null> {
    const layers = side.filter((l) => l.h.trim() !== "" && l.er.trim() !== "");
    if (layers.length === 0) return null;
    const r = await fetch("/api/materials/series_reduce", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        layers: layers.map((l) => ({
          h: l.h,
          er: parseFloat(l.er),
          tan_delta: parseFloat(l.tan_delta || "0"),
          name: l.name || null,
        })),
      }),
    });
    if (!r.ok) {
      throw new Error(`series_reduce: ${r.status} ${await r.text()}`);
    }
    const body = (await r.json()) as { h_total_m: number; er_eq: number; tan_eq: number };
    return { h: body.h_total_m, er: body.er_eq, tan: body.tan_eq };
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      const aboveRes = above.length > 0 ? await reduceSide(above) : null;
      const belowRes = below.length > 0 ? await reduceSide(below) : null;
      const update: Record<string, unknown> = { ...(geometry ?? {}) };
      if (aboveRes) {
        update.H1 = formatMeters(aboveRes.h, unit);
        update.er_above = aboveRes.er;
        update.tan_delta_above = aboveRes.tan;
      }
      if (belowRes) {
        update.H2 = formatMeters(belowRes.h, unit);
        update.er_below = belowRes.er;
        update.tan_delta_below = belowRes.tan;
      }
      // Also fill bulk er if it's not set (asymmetric model requires it).
      if (!update.er) {
        const r = aboveRes?.er ?? belowRes?.er ?? 4.0;
        update.er = r;
      }
      setGeometry(update);
      onClose();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function loadL3SIG1Preset() {
    setAbove([{ h: "3.5mil", er: "4.2", tan_delta: "0.020", name: "Core" }]);
    setBelow(PRESET_L3_SIG1.map((l) => ({ ...l })));
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
      <div className="bg-navy-950 border border-navy-700 rounded-lg max-w-4xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-navy-800">
          <span className="text-sm font-semibold text-slate-200">
            Stackup editor — multi-layer dielectric (asymmetric stripline)
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={loadL3SIG1Preset}
              className="text-xs text-slate-400 hover:text-emerald-400"
              title="Load Prepreg / voided-L4 / Core preset"
            >
              load L3 SIG1 preset
            </button>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-100 px-2"
              aria-label="close"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 md:grid-cols-2 gap-6">
          <StackTable
            title="Above strip (top → strip)"
            layers={above}
            onChange={(idx, patch) => updateLayer("above", idx, patch)}
            onAdd={() => addLayer("above")}
            onRemove={(idx) => removeLayer("above", idx)}
          />
          <StackTable
            title="Below strip (strip → bottom)"
            layers={below}
            onChange={(idx, patch) => updateLayer("below", idx, patch)}
            onAdd={() => addLayer("below")}
            onRemove={(idx) => removeLayer("below", idx)}
          />
        </div>

        {err && (
          <div className="mx-4 mb-3 bg-rose-950/40 border border-rose-800 rounded p-2 text-xs text-rose-300">
            {err}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 px-4 py-3 border-t border-navy-800">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-slate-300 hover:text-slate-100"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="px-4 py-1.5 text-sm bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 text-white rounded"
          >
            {busy ? "Reducing…" : "Apply to form"}
          </button>
        </div>
      </div>
    </div>
  );
}

function StackTable({
  title,
  layers,
  onChange,
  onAdd,
  onRemove,
}: {
  title: string;
  layers: Layer[];
  onChange: (idx: number, patch: Partial<Layer>) => void;
  onAdd: () => void;
  onRemove: (idx: number) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wider text-slate-500">{title}</div>
      <table className="w-full text-xs">
        <thead className="text-slate-500">
          <tr>
            <th className="text-left pb-1">name</th>
            <th className="text-left pb-1">h</th>
            <th className="text-left pb-1">εr</th>
            <th className="text-left pb-1">tan_δ</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {layers.map((layer, i) => (
            <tr key={i}>
              <td>
                <input
                  value={layer.name}
                  onChange={(e) => onChange(i, { name: e.target.value })}
                  className="w-full bg-navy-900 border border-navy-700 rounded px-1.5 py-1 text-slate-100"
                  placeholder="Prepreg"
                />
              </td>
              <td>
                <input
                  value={layer.h}
                  onChange={(e) => onChange(i, { h: e.target.value })}
                  className="w-20 bg-navy-900 border border-navy-700 rounded px-1.5 py-1 text-slate-100"
                  placeholder="5.3mil"
                />
              </td>
              <td>
                <input
                  value={layer.er}
                  onChange={(e) => onChange(i, { er: e.target.value })}
                  className="w-16 bg-navy-900 border border-navy-700 rounded px-1.5 py-1 text-slate-100"
                  placeholder="3.7"
                />
              </td>
              <td>
                <input
                  value={layer.tan_delta}
                  onChange={(e) => onChange(i, { tan_delta: e.target.value })}
                  className="w-16 bg-navy-900 border border-navy-700 rounded px-1.5 py-1 text-slate-100"
                  placeholder="0.02"
                />
              </td>
              <td className="text-right">
                <button
                  onClick={() => onRemove(i)}
                  className="text-slate-500 hover:text-rose-400 px-1"
                  aria-label="remove layer"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        onClick={onAdd}
        className="text-xs text-emerald-400 hover:text-emerald-300"
      >
        + add layer
      </button>
    </div>
  );
}
