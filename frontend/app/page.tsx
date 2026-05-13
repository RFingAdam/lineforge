"use client";

import { useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { GeometryPanel } from "@/components/GeometryPanel";
import { Logo } from "@/components/Logo";
import { ResultsPanel } from "@/components/ResultsPanel";
import { StatusCluster } from "@/components/StatusCluster";
import { Tour } from "@/components/Tour";
import { UnitToggle } from "@/components/UnitToggle";

type MobileTab = "chat" | "geometry" | "results";

const TABS: { id: MobileTab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "geometry", label: "Geometry" },
  { id: "results", label: "Results" },
];

export default function Page() {
  const [tab, setTab] = useState<MobileTab>("geometry");

  function paneClass(id: MobileTab): string {
    const visible = tab === id ? "flex" : "hidden";
    return `${visible} lg:flex`;
  }

  return (
    <div className="min-h-screen flex flex-col bg-canvas">
      {/* ── topbar ────────────────────────────────────────────────────── */}
      <header
        role="banner"
        className="glass sticky top-0 z-40 px-4 h-14 flex items-center gap-4"
      >
        <div className="flex items-center gap-3 min-w-0">
          <Logo size={26} />
          <div className="flex flex-col min-w-0">
            <h1 className="font-display text-base font-semibold text-slate-100 leading-none">
              lineforge
            </h1>
            <p className="text-[11px] text-slate-400 leading-none mt-0.5 truncate">
              Transmission-Line Design Studio
            </p>
          </div>
        </div>

        <div className="flex-1" aria-hidden="true" />

        <div className="flex items-center gap-3">
          <div className="hidden md:flex">
            <StatusCluster />
          </div>
          <Tour />
          <UnitToggle />
        </div>
      </header>

      {/* ── mobile pane switcher ─────────────────────────────────────── */}
      <div
        role="tablist"
        aria-label="Workspace panes"
        className="lg:hidden flex items-center gap-1.5 px-3 pt-3"
      >
        {TABS.map((t) => {
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={active}
              aria-controls={`pane-${t.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setTab(t.id)}
              className={
                "focus-ring rounded-full px-3 py-1 text-xs font-medium border " +
                (active
                  ? "bg-surface-overlay text-slate-100 border-border-strong"
                  : "bg-surface-raised text-slate-400 hover:text-slate-200 border-border-subtle")
              }
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── main workspace ───────────────────────────────────────────── */}
      <main
        role="main"
        className="flex-1 flex flex-col lg:grid lg:grid-cols-12 gap-3 p-3 overflow-hidden"
      >
        <section
          id="pane-chat"
          role="region"
          aria-label="Chat"
          className={`panel overflow-hidden lg:col-span-4 flex-col min-h-0 ${paneClass("chat")}`}
        >
          <h2 className="sr-only">Chat</h2>
          <ErrorBoundary label="chat panel">
            <ChatPanel />
          </ErrorBoundary>
        </section>

        <section
          id="pane-geometry"
          role="region"
          aria-label="Geometry"
          className={`panel overflow-hidden lg:col-span-3 flex-col min-h-0 ${paneClass("geometry")}`}
        >
          <h2 className="sr-only">Geometry</h2>
          <ErrorBoundary label="geometry panel">
            <GeometryPanel />
          </ErrorBoundary>
        </section>

        <section
          id="pane-results"
          role="region"
          aria-label="Results"
          className={`panel overflow-hidden lg:col-span-5 flex-col min-h-0 ${paneClass("results")}`}
        >
          <h2 className="sr-only">Results</h2>
          <ErrorBoundary label="results panel">
            <ResultsPanel />
          </ErrorBoundary>
        </section>
      </main>

      {/* ── footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-border-subtle px-4 py-2 text-[11px] text-slate-500 flex items-center justify-between">
        <span>lineforge · AGPL-3.0</span>
        <a
          href="https://github.com/RFingAdam/lineforge"
          target="_blank"
          rel="noreferrer noopener"
          className="focus-ring rounded-xs hover:text-slate-300"
        >
          github.com/RFingAdam/lineforge
        </a>
      </footer>
    </div>
  );
}
