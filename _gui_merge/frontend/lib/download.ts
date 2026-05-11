/**
 * Tiny helpers for browser-side file downloads. No deps; works against
 * any string/Blob payload by creating an object URL and clicking a
 * temporary <a> element.
 */

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Free the URL once the click navigation has been dispatched.
  setTimeout(() => URL.revokeObjectURL(url), 100);
}

export function downloadText(text: string, filename: string, mime = "text/plain"): void {
  downloadBlob(new Blob([text], { type: mime }), filename);
}

export function downloadJSON(data: unknown, filename: string): void {
  downloadText(JSON.stringify(data, null, 2), filename, "application/json");
}

/** Serialize a live SVG element (with all its computed attributes) and
 * download it as an .svg file. Pass the actual <svg> DOM node. */
export function downloadSVG(svg: SVGElement, filename: string): void {
  const xml = new XMLSerializer().serializeToString(svg);
  // Ensure the doctype + xmlns survive the round-trip — some browsers
  // strip them when constructing via React.
  const blob = new Blob(
    [`<?xml version="1.0" standalone="no"?>\n${xml.includes("xmlns") ? xml : xml.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"')}`],
    { type: "image/svg+xml" },
  );
  downloadBlob(blob, filename);
}

/** Convert a base64 data-URI PNG to a Blob and download. */
export function downloadDataUri(dataUri: string, filename: string): void {
  // dataUri = "data:image/png;base64,xxx..."
  const m = dataUri.match(/^data:([^;]+);base64,(.*)$/);
  if (!m) return;
  const mime = m[1];
  const bin = atob(m[2]);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  downloadBlob(new Blob([arr], { type: mime }), filename);
}

/** Make a timestamped filename like "stripline_asymmetric-2026-05-08T14-32-19.json" */
export function timestampedFilename(stem: string, ext: string): string {
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `${stem}-${ts}.${ext}`;
}
