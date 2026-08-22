"use client";

import { useEffect, useState } from "react";

/**
 * Right-side cluster of small status pills shown in the topbar.
 *
 * Pills:
 *  - **backend**: polls `/api/health` every 5s. amber on initial load,
 *    green when the endpoint returns ok, red on error.
 *  - **MCP**: there is no global WS-state selector yet, so we report a
 *    passive "idle" state for now. A follow-up agent can wire this up to
 *    a `wsConnected` selector once the chat store exposes one.
 *  - **version**: small monospace badge reading
 *    `process.env.NEXT_PUBLIC_LINEFORGE_VERSION` at build time.
 *
 * The pills are presentational only. They never block interaction and
 * they degrade gracefully when the backend is down.
 */

type Health = "ok" | "down" | "loading";

const PILL_BASE =
  "text-[11px] uppercase tracking-wide rounded-full px-2 py-0.5 " +
  "border border-border-subtle bg-surface-raised " +
  "flex items-center gap-1.5 select-none";

function Dot({ tone }: { tone: "success" | "warn" | "danger" | "info" | "muted" }) {
  // Map a logical tone → background class. We list every class explicitly so
  // Tailwind's JIT picks them up rather than constructing names dynamically.
  const cls =
    tone === "success"
      ? "bg-success"
      : tone === "warn"
      ? "bg-warn"
      : tone === "danger"
      ? "bg-danger"
      : tone === "info"
      ? "bg-info"
      : "bg-slate-500";
  return <span aria-hidden="true" className={`inline-block w-1.5 h-1.5 rounded-full ${cls}`} />;
}

function useBackendHealth(): Health {
  const [state, setState] = useState<Health>("loading");

  useEffect(() => {
    let cancelled = false;

    async function ping() {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        if (cancelled) return;
        setState(res.ok ? "ok" : "down");
      } catch {
        if (!cancelled) setState("down");
      }
    }

    ping();
    const id = window.setInterval(ping, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return state;
}

function BackendPill() {
  const health = useBackendHealth();
  const tone = health === "ok" ? "success" : health === "down" ? "danger" : "warn";
  const label = health === "ok" ? "backend ok" : health === "down" ? "backend down" : "backend…";
  const live = health === "down" ? "assertive" : "polite";

  return (
    <span
      className={PILL_BASE}
      role="status"
      aria-live={live}
      title={
        health === "ok"
          ? "Backend /api/health responding ok"
          : health === "down"
          ? "Backend /api/health is not responding"
          : "Checking backend /api/health…"
      }
    >
      <Dot tone={tone} />
      <span className="text-slate-200">{label}</span>
    </span>
  );
}

function McpPill() {
  // Placeholder: see file-level comment. Renders as a neutral idle pill so
  // the topbar layout is stable until a real WS connection selector lands.
  return (
    <span
      className={PILL_BASE}
      title="MCP chat status: wiring pending"
      aria-label="MCP idle"
    >
      <Dot tone="muted" />
      <span className="text-slate-400">mcp idle</span>
    </span>
  );
}

function VersionPill() {
  const version = process.env.NEXT_PUBLIC_LINEFORGE_VERSION ?? "dev";
  return (
    <span
      className={`${PILL_BASE} font-mono`}
      aria-label={`lineforge version ${version}`}
      title={`lineforge ${version}`}
    >
      <span className="text-slate-300">v{version}</span>
    </span>
  );
}

export function StatusCluster() {
  return (
    <div className="flex items-center gap-2" role="group" aria-label="System status">
      <BackendPill />
      <McpPill />
      <VersionPill />
    </div>
  );
}
