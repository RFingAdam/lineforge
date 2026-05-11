"use client";

import { useEffect, useState } from "react";
import {
  getPreferredUnit,
  setPreferredUnit,
  type LengthUnit,
} from "@/lib/units";
import { useGuiStore } from "@/lib/store";

const UNITS: LengthUnit[] = ["mil", "mm"];

/**
 * Small pill-toggle in the header that flips the global length unit.
 *
 * On flip:
 * 1. Persists the new unit to localStorage.
 * 2. Pokes the GuiStore so subscribers re-render. We keep form values as
 *    user-typed strings (e.g. "6mil"); the toggle changes how new values
 *    are interpreted and how display defaults work, not the stored form
 *    state. Components that want to *re-format* values across the toggle
 *    can subscribe to ``unit`` and re-run their own conversion.
 */
export function UnitToggle() {
  const unit = useGuiStore((s) => s.unit);
  const setUnit = useGuiStore((s) => s.setUnit);
  const [mounted, setMounted] = useState(false);

  // Hydrate from localStorage once on mount (avoids SSR/CSR mismatch).
  useEffect(() => {
    const u = getPreferredUnit();
    setUnit(u);
    setMounted(true);
  }, [setUnit]);

  if (!mounted) {
    return (
      <div className="flex items-center gap-1 text-xs text-slate-500">
        <span className="opacity-0">unit</span>
      </div>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Length unit"
      className="flex items-center gap-0 rounded-md border border-navy-700 overflow-hidden bg-navy-900 text-xs"
    >
      {UNITS.map((u) => {
        const active = u === unit;
        return (
          <button
            key={u}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => {
              setPreferredUnit(u);
              setUnit(u);
            }}
            className={
              active
                ? "px-2 py-1 bg-emerald-600 text-white font-medium"
                : "px-2 py-1 text-slate-300 hover:bg-navy-800"
            }
          >
            {u}
          </button>
        );
      })}
    </div>
  );
}
