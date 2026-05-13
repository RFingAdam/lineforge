"use client";

import { useState, type ReactNode } from "react";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={`transition-transform ${open ? "rotate-90" : "rotate-0"}`}
    >
      <path
        d="M9 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export interface SectionProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
}

/**
 * Group of related form fields with a small all-caps legend. When
 * `collapsible`, the legend doubles as a toggle button with a chevron.
 *
 * Uses <fieldset> + <legend> so the grouping is conveyed to assistive tech.
 */
export function Section({
  title,
  subtitle,
  children,
  collapsible = false,
  defaultOpen = true,
}: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const visible = !collapsible || open;

  const legendInner = (
    <>
      <span className="flex items-center gap-2">
        {collapsible && <Chevron open={open} />}
        <span>{title}</span>
      </span>
      {subtitle && (
        <span className="text-[10px] normal-case tracking-normal text-slate-500 italic">
          {subtitle}
        </span>
      )}
    </>
  );

  return (
    <fieldset className="space-y-2 min-w-0">
      <legend className="w-full">
        {collapsible ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex items-center justify-between gap-2 w-full text-[11px]
                       uppercase tracking-widest text-slate-400 hover:text-slate-200
                       border-b border-border-subtle pb-1.5 mb-2 transition-colors
                       focus-ring rounded-xs"
          >
            {legendInner}
          </button>
        ) : (
          <div
            className="flex items-center justify-between gap-2 w-full text-[11px]
                       uppercase tracking-widest text-slate-400
                       border-b border-border-subtle pb-1.5 mb-2"
          >
            {legendInner}
          </div>
        )}
      </legend>
      {visible && <div className="space-y-2.5">{children}</div>}
    </fieldset>
  );
}
