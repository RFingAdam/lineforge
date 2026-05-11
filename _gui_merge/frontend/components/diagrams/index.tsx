"use client";

import { useRef } from "react";
import { downloadSVG, timestampedFilename } from "@/lib/download";
import { useGuiStore } from "@/lib/store";
import { BroadsideCoupledSVG } from "./BroadsideCoupledSVG";
import { CPWGSVG } from "./CPWGSVG";
import { DiffPairSVG } from "./DiffPairSVG";
import { EmbeddedMicrostripSVG } from "./EmbeddedMicrostripSVG";
import { MicrostripSVG } from "./MicrostripSVG";
import { StriplineAsymmetricSVG } from "./StriplineAsymmetricSVG";
import { StriplineSymmetricSVG } from "./StriplineSymmetricSVG";
import { ThreeWireSVG } from "./ThreeWireSVG";

/** Picks the right SVG cross-section component for the current geometry,
 * with a small "↓ SVG" download button overlaid in the top-right. */
export function GeometryDiagram() {
  const geometry = useGuiStore((s) => s.geometry);
  const unit = useGuiStore((s) => s.unit);
  const type = (geometry?.type as string | undefined) ?? "";
  const ref = useRef<HTMLDivElement>(null);

  function exportSvg() {
    const svg = ref.current?.querySelector("svg");
    if (svg) downloadSVG(svg as SVGElement, timestampedFilename(`atlc3-${type || "diagram"}`, "svg"));
  }

  if (!type) {
    return (
      <div className="flex items-center justify-center h-full bg-navy-950 rounded text-slate-500 text-sm">
        Select a geometry to see the cross-section.
      </div>
    );
  }

  let inner: React.ReactNode;
  switch (type) {
    case "microstrip":
      inner = <MicrostripSVG geometry={geometry} unit={unit} />;
      break;
    case "embedded_microstrip":
      inner = <EmbeddedMicrostripSVG geometry={geometry} unit={unit} />;
      break;
    case "stripline_symmetric":
      inner = <StriplineSymmetricSVG geometry={geometry} unit={unit} />;
      break;
    case "stripline_asymmetric":
      inner = <StriplineAsymmetricSVG geometry={geometry} unit={unit} />;
      break;
    case "cpwg":
      inner = <CPWGSVG geometry={geometry} unit={unit} />;
      break;
    case "edge_coupled_diff_microstrip":
      inner = <DiffPairSVG geometry={geometry} unit={unit} stripline={false} />;
      break;
    case "edge_coupled_diff_stripline":
      inner = <DiffPairSVG geometry={geometry} unit={unit} stripline={true} />;
      break;
    case "broadside_coupled_diff_stripline":
      inner = <BroadsideCoupledSVG geometry={geometry} unit={unit} />;
      break;
    case "three_wire":
      inner = <ThreeWireSVG geometry={geometry} unit={unit} />;
      break;
    default:
      inner = (
        <div className="flex items-center justify-center h-full bg-navy-950 rounded text-slate-500 text-sm">
          No diagram available for type &ldquo;{type}&rdquo;.
        </div>
      );
  }

  return (
    <div ref={ref} className="relative">
      {inner}
      <button
        onClick={exportSvg}
        title="Download cross-section as SVG"
        className="absolute top-1 right-1 text-[10px] text-slate-500 hover:text-emerald-400 bg-navy-950/70 backdrop-blur px-1.5 py-0.5 rounded"
      >
        ↓ SVG
      </button>
    </div>
  );
}
