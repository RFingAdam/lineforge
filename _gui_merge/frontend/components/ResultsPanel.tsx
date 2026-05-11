"use client";

import { downloadJSON, timestampedFilename } from "@/lib/download";
import { useGuiStore } from "@/lib/store";
import { ResultSkeleton } from "./Skeleton";
import { DiffResultCard } from "./results/DiffResultCard";
import { FieldPlotCanvas } from "./results/FieldPlotCanvas";
import { SweepChart } from "./results/SweepChart";
import { ThreeWireResultCard } from "./results/ThreeWireResultCard";
import { TLineResultCard } from "./results/TLineResultCard";

export function ResultsPanel() {
  const result = useGuiStore((s) => s.lastResult);
  const sweep = useGuiStore((s) => s.sweepConfig);
  const sweepResults = useGuiStore((s) => s.sweepResults);
  const geometry = useGuiStore((s) => s.geometry);
  const frequency = useGuiStore((s) => s.frequency);
  const isSolving = useGuiStore((s) => s.isSolving);

  function exportJson() {
    const stem = (geometry?.type as string | undefined) ?? "atlc3";
    downloadJSON(
      {
        timestamp: new Date().toISOString(),
        geometry,
        frequency: frequency || null,
        result,
        sweep_config: sweep,
        sweep_results: sweepResults,
      },
      timestampedFilename(stem, "json"),
    );
  }

  return (
    <div className="flex h-full flex-col bg-navy-950">
      <div className="px-4 py-2 border-b border-navy-800 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-slate-500">Results</span>
        {(result || sweepResults) && (
          <button
            onClick={exportJson}
            title="Download geometry + result as JSON"
            className="text-[11px] text-slate-400 hover:text-emerald-400"
          >
            ↓ JSON
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {isSolving && !result && <ResultSkeleton />}
        {!isSolving && !result && !sweep && <EmptyState />}

        {result && <ResultDispatcher result={result} />}

        {result && (result._kind === "TLineResult" || result._kind === "DiffResult" || result._kind === "ThreeWireResult" || result._kind === "CGPResult") && (
          <FieldPlotCanvas />
        )}

        <SweepChart />

        {result && (
          <details className="text-xs text-slate-500">
            <summary className="cursor-pointer hover:text-slate-300">
              raw result JSON
            </summary>
            <pre className="mt-2 bg-navy-950 border border-navy-800 rounded p-2 overflow-x-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

function ResultDispatcher({ result }: { result: Record<string, unknown> }) {
  const kind = result._kind as string | undefined;
  switch (kind) {
    case "DiffResult":
      return <DiffResultCard result={result} />;
    case "ThreeWireResult":
      return <ThreeWireResultCard result={result} />;
    case "TLineResult":
    case "CGPResult":
      return <TLineResultCard result={result} />;
    default:
      return <TLineResultCard result={result} />;
  }
}

function EmptyState() {
  return (
    <div className="text-slate-500 text-sm">
      No result yet. Configure a geometry on the left and press{" "}
      <span className="text-emerald-400">Calculate Z₀</span>, or ask the chat agent.
    </div>
  );
}
