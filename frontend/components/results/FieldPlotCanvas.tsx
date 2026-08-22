"use client";

import { useEffect, useState } from "react";
import { downloadDataUri, timestampedFilename } from "@/lib/download";
import { useGuiStore } from "@/lib/store";
import { Button, Card } from "@/components/ui";

type FieldKind = "V" | "E" | "D" | "T";
const KINDS: FieldKind[] = ["V", "E", "D", "T"];

const KIND_LABEL: Record<FieldKind, string> = {
  V: "voltage",
  E: "E-field",
  D: "D-field",
  T: "loss density",
};

/** Long-form caption shown under the rendered plot. Aimed at engineers
 *  who already speak field-solver language but might be flipping through
 *  the four kinds quickly. */
const KIND_CAPTION: Record<FieldKind, string> = {
  V: "V: Electric potential (volts), normalized to the energized conductor.",
  E: "E: Electric-field magnitude |E| (V/m), log-compressed for visibility.",
  D: "D: Electric-flux density |D| = ε·|E| (C/m²); highlights dielectric loading.",
  T: "T: Local dielectric loss density (W/m³); proxy for tan(δ) hot spots.",
};

/** Unit annotation shown at the bottom of the colorbar legend. */
const KIND_UNIT: Record<FieldKind, string> = {
  V: "V",
  E: "V/m",
  D: "C/m²",
  T: "W/m³",
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

  if (!geometry) {
    return (
      <Card
        tone="raised"
        className="h-40 flex items-center justify-center text-slate-500 text-sm"
      >
        No field plot yet
      </Card>
    );
  }
  const png = cache[key];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-slate-500">Field plot</div>
        <KindTabs kind={kind} onChange={setKind} />
      </div>

      <Card tone="raised" padded={false} className="overflow-hidden">
        {/* header bar: kind label + download */}
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle">
          <div className="text-[11px] uppercase tracking-wider text-slate-400 font-mono">
            {kind} · {KIND_LABEL[kind]}
          </div>
          <Button
            variant="ghost"
            size="sm"
            disabled={!png}
            onClick={() =>
              png &&
              downloadDataUri(
                png,
                timestampedFilename(`lineforge-field-${kind.toLowerCase()}`, "png"),
              )
            }
            title="Download field plot as PNG"
            leftIcon={<DownloadIcon />}
            aria-label="Download field plot as PNG"
          >
            PNG
          </Button>
        </div>

        {/* plot area: image + colorbar legend, with absolute-positioned chrome */}
        <div className="relative bg-canvas">
          <div className="min-h-40 flex items-center justify-center p-2">
            {busy && !png && (
              <div className="w-full px-4 py-6 space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{progress?.stage ?? "submitting"}…</span>
                  {progress && (
                    <span className="font-mono text-slate-500">
                      {Math.round(progress.frac * 100)}%
                    </span>
                  )}
                </div>
                <div className="h-1.5 bg-surface-raised rounded overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all duration-200"
                    style={{ width: `${(progress?.frac ?? 0.05) * 100}%` }}
                  />
                </div>
              </div>
            )}
            {err && !busy && (
              <div className="text-xs text-danger p-3 break-words">{err}</div>
            )}
            {png && (
              // The PNG is a base64 data URI served by the field-plot API.
              // We intentionally use a plain <img> rather than next/image
              // because: (a) the source is a data URI, not a URL Next can
              // optimize, and (b) we need `image-rendering: pixelated` for
              // crisp grid-cell edges, which next/image strips. ESLint will
              // warn: that's a known acceptance, see A3 report.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={png}
                alt={`${KIND_LABEL[kind]} field plot`}
                className="max-w-full max-h-80 object-contain"
                style={{ imageRendering: "pixelated" }}
              />
            )}
          </div>

          {png && <Colorbar kind={kind} />}
        </div>

        {/* caption */}
        <div className="px-3 py-1.5 border-t border-border-subtle text-[11px] text-slate-400">
          {KIND_CAPTION[kind]}
        </div>
      </Card>

      <div className="text-[11px] text-slate-500">
        Press V / E / D / T to switch (atlc2-style).
      </div>
    </div>
  );
}

/** Field-kind selector pills, styled to match the rest of the design
 *  system. Native <button>s preserve keyboard / a11y for free: Tab
 *  focuses, Enter/Space activates, V/E/D/T hotkeys fire via the global
 *  keydown listener above. */
function KindTabs({
  kind,
  onChange,
}: {
  kind: FieldKind;
  onChange: (k: FieldKind) => void;
}) {
  return (
    <div
      className="flex items-center gap-0.5 bg-surface-raised rounded-md p-0.5"
      role="tablist"
      aria-label="Field kind"
    >
      {KINDS.map((k) => {
        const active = k === kind;
        return (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(k)}
            title={`${KIND_LABEL[k]} (key: ${k})`}
            className={[
              "px-2 py-0.5 rounded-sm text-xs font-mono font-medium",
              "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              active
                ? "bg-surface-overlay text-slate-100"
                : "text-slate-400 hover:text-slate-200",
            ].join(" ")}
          >
            {k}
          </button>
        );
      })}
    </div>
  );
}

/** Vertical colorbar legend to the right of the plot.
 *
 *  Note: the field-plot API returns a baked PNG with no numeric value
 *  range exposed, so this bar is intentionally *qualitative*. It shows
 *  colormap direction (low → high) and the units the kind reports, not
 *  a numeric scale. For absolute values, refer to the on-image colorbar
 *  produced by the backend. */
function Colorbar({ kind }: { kind: FieldKind }) {
  return (
    <div
      className="absolute top-2 right-2 flex flex-col items-center gap-1 pointer-events-none select-none"
      aria-hidden="true"
    >
      <span className="text-[10px] font-mono text-slate-300">high</span>
      <div
        className="w-3 h-32 rounded-sm border border-border-strong"
        style={{
          // Approximate viridis-via-token-palette: warn → accent → info.
          // Reads legibly on the dark canvas and stays inside the
          // design system without pulling raw hex into the component.
          background:
            "linear-gradient(to bottom, #fbbf24 0%, #22d3ee 50%, #38bdf8 100%)",
        }}
      />
      <span className="text-[10px] font-mono text-slate-300">low</span>
      <span className="text-[10px] font-mono text-slate-500">
        {KIND_UNIT[kind]}
      </span>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
