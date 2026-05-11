"use client";

import { useEffect, useState } from "react";
import { downloadDataUri, timestampedFilename } from "@/lib/download";
import { useGuiStore } from "@/lib/store";

type FieldKind = "V" | "E" | "D" | "T";
const KINDS: FieldKind[] = ["V", "E", "D", "T"];

const KIND_LABEL: Record<FieldKind, string> = {
  V: "voltage",
  E: "E-field",
  D: "D-field",
  T: "loss density",
};

/**
 * Tabbed field-plot view. Lazily fetches a PNG from
 * /api/solve/field_plot for the current geometry whenever the user clicks
 * a tab; caches per-(geometry, kind) so re-tabbing is instant.
 */
export function FieldPlotCanvas() {
  const geometry = useGuiStore((s) => s.geometry);
  const [kind, setKind] = useState<FieldKind>("E");
  const [cache, setCache] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ stage: string; frac: number } | null>(null);

  const key = geometry ? JSON.stringify(geometry) + ":" + kind : "";

  useEffect(() => {
    if (!geometry || !key || cache[key]) return;
    let cancelled = false;
    let ws: WebSocket | null = null;
    setBusy(true);
    setErr(null);
    setProgress({ stage: "submitting", frac: 0.01 });

    const body =
      typeof geometry.usermap_uri === "string"
        ? { usermap_uri: geometry.usermap_uri, field_kind: kind }
        : { geometry, field_kind: kind };

    // Submit the async task, then attach a progress WebSocket.
    fetch("/api/solve/field_plot/async", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`field_plot: ${r.status} ${await r.text()}`);
        return r.json();
      })
      .then((j: { task_id: string }) => {
        if (cancelled) return;
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${proto}//${window.location.host}/ws/progress/${j.task_id}`);
        ws.onmessage = (ev) => {
          if (cancelled) return;
          const msg = JSON.parse(ev.data) as
            | { type: "progress"; stage: string; frac: number }
            | { type: "result"; result: { png_data_uri: string } }
            | { type: "error"; error: string };
          if (msg.type === "progress") {
            setProgress({ stage: msg.stage, frac: msg.frac });
          } else if (msg.type === "result") {
            setCache((c) => ({ ...c, [key]: msg.result.png_data_uri }));
            setBusy(false);
            setProgress(null);
          } else if (msg.type === "error") {
            setErr(msg.error);
            setBusy(false);
            setProgress(null);
          }
        };
        ws.onerror = () => {
          if (!cancelled) setErr("progress WebSocket dropped");
        };
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
        setBusy(false);
        setProgress(null);
      });

    return () => {
      cancelled = true;
      ws?.close();
    };
  }, [key, geometry, kind, cache]);

  // atlc2 keystroke shortcuts: V/E/D/T while panel has focus
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        document.activeElement instanceof HTMLInputElement ||
        document.activeElement instanceof HTMLTextAreaElement ||
        document.activeElement instanceof HTMLSelectElement
      ) {
        return;
      }
      const k = e.key.toUpperCase();
      if ((KINDS as string[]).includes(k)) {
        setKind(k as FieldKind);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!geometry) return null;
  const png = cache[key];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Field plot</div>
        <div className="flex items-center gap-1 text-xs">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setKind(k)}
              className={
                k === kind
                  ? "px-2 py-0.5 rounded bg-emerald-600 text-white"
                  : "px-2 py-0.5 rounded text-slate-400 hover:text-slate-100"
              }
              title={`${KIND_LABEL[k]} (key: ${k})`}
            >
              {k}
            </button>
          ))}
          {png && (
            <button
              type="button"
              onClick={() =>
                downloadDataUri(png, timestampedFilename(`atlc3-field-${kind.toLowerCase()}`, "png"))
              }
              title="Download field plot as PNG"
              className="ml-1 text-slate-400 hover:text-emerald-400"
            >
              ↓
            </button>
          )}
        </div>
      </div>
      <div className="bg-navy-950 border border-navy-800 rounded min-h-32 flex items-center justify-center overflow-hidden">
        {busy && !png && (
          <div className="w-full px-6 py-6 space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>{progress?.stage ?? "submitting"}…</span>
              {progress && (
                <span className="font-mono text-slate-500">
                  {Math.round(progress.frac * 100)}%
                </span>
              )}
            </div>
            <div className="h-1.5 bg-navy-800 rounded overflow-hidden">
              <div
                className="h-full bg-cyan-500 transition-all duration-200"
                style={{ width: `${(progress?.frac ?? 0.05) * 100}%` }}
              />
            </div>
          </div>
        )}
        {err && !busy && (
          <div className="text-xs text-rose-400 p-3 break-words">{err}</div>
        )}
        {png && (
          <img
            src={png}
            alt={`${KIND_LABEL[kind]} field plot`}
            className="max-w-full max-h-80 object-contain"
            style={{ imageRendering: "pixelated" }}
          />
        )}
      </div>
      <div className="text-[11px] text-slate-500">
        Press V / E / D / T to switch (atlc2-style).
      </div>
    </div>
  );
}
