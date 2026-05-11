"use client";

import { useState } from "react";
import { useGuiStore } from "@/lib/store";

type UploadResponse = {
  uri: string;
  uid: string;
  shape: [number, number];
  pixel_width_m: number;
  name: string;
  preview_png_base64: string;
};

/**
 * atlc2-style custom-usermap loader. The user drops a BMP, types a pixel
 * width, and we POST it to /api/usermap/upload. The returned URI lives in
 * the GUI state's geometry as ``{usermap_uri: "atlc://..."}``, which the
 * Calculate button (in the Built-in panel) routes to /api/solve/calculate
 * with the bitmap solver.
 */
export function CustomUsermapPanel() {
  const setGeometry = useGuiStore((s) => s.setGeometry);
  const [pixelWidth, setPixelWidth] = useState("0.1mm");
  const [name, setName] = useState("custom_usermap");
  const [uploaded, setUploaded] = useState<UploadResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    setBusy(true);
    setErr(null);
    try {
      const buf = await file.arrayBuffer();
      const b64 = arrayBufferToBase64(buf);
      const r = await fetch("/api/usermap/upload", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          bmp_base64: b64,
          pixel_width: pixelWidth,
          name: name || file.name,
        }),
      });
      if (!r.ok) {
        const body = await r.text();
        try {
          const j = JSON.parse(body);
          throw new Error(typeof j.detail === "string" ? j.detail : body);
        } catch {
          throw new Error(`upload failed: ${r.status} ${body}`);
        }
      }
      const data = (await r.json()) as UploadResponse;
      setUploaded(data);
      // Stash the URI in the GUI's geometry so the Calculate button uses it.
      setGeometry({ usermap_uri: data.uri, name: data.name });
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="space-y-3 text-sm">
      <p className="text-xs text-slate-400">
        Drop or pick an atlc-style BMP/PNG. Red pixels = signal (+1), blue =
        signal (−1), green = ground (0). The bitmap solver runs on upload.
      </p>

      <label className="block">
        <span className="block text-xs text-slate-400 mb-1">Pixel width</span>
        <input
          type="text"
          value={pixelWidth}
          onChange={(e) => setPixelWidth(e.target.value)}
          placeholder="0.1mm"
          className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1.5 text-slate-100"
        />
      </label>

      <label className="block">
        <span className="block text-xs text-slate-400 mb-1">Name</span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full bg-navy-900 border border-navy-700 rounded px-2 py-1.5 text-slate-100"
        />
      </label>

      <div
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={
          "rounded border-2 border-dashed p-6 text-center text-xs transition-colors " +
          (dragOver
            ? "border-emerald-500 bg-emerald-950/30 text-emerald-300"
            : "border-navy-700 bg-navy-900 text-slate-400")
        }
      >
        Drop a BMP/PNG here, or
        <label className="ml-1 text-emerald-400 underline cursor-pointer">
          browse
          <input
            type="file"
            accept="image/bmp,image/png,.bmp,.png"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
            }}
          />
        </label>
      </div>

      {busy && <div className="text-xs text-slate-400">Uploading…</div>}
      {err && (
        <div className="bg-rose-950/40 border border-rose-800 rounded p-2 text-xs text-rose-300">
          {err}
        </div>
      )}

      {uploaded && (
        <div className="bg-navy-900 border border-navy-800 rounded p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">{uploaded.name}</span>
            <span className="font-mono text-slate-500">
              {uploaded.shape[1]}×{uploaded.shape[0]}px
            </span>
          </div>
          <img
            src={uploaded.preview_png_base64}
            alt="usermap preview"
            className="w-full max-h-64 object-contain bg-navy-950 rounded"
          />
          <div className="text-[11px] text-slate-500 break-all">{uploaded.uri}</div>
        </div>
      )}
    </div>
  );
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let str = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    str += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + chunkSize)));
  }
  return btoa(str);
}
