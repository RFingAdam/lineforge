"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "atlc3-gui:tour-seen";

const STEPS: Array<{ title: string; body: string }> = [
  {
    title: "1. Pick a geometry",
    body:
      "Use the Built-in tab and the Type dropdown for one of the 9 standard cross-sections (microstrip, asymmetric stripline, three-wire, etc.), or drop a BMP into the Custom BMP tab for an atlc2-style usermap.",
  },
  {
    title: "2. Edit dimensions",
    body:
      "Type W / H / T / etc. in the form. Bare numbers auto-suffix the current unit (toggle mil ↔ mm in the header). The cross-section diagram above the form scales live as you type.",
  },
  {
    title: "3. Pick a material",
    body:
      "The Material dropdown auto-fills εr and tan_δ from the 18-vendor laminate catalog. For multi-layer stackups (e.g. Prepreg + voided plane + Core on the L3 SIG1 case), open the “Edit multi-layer stack…” modal — there’s a one-click L3 SIG1 preset.",
  },
  {
    title: "4. Calculate Z₀",
    body:
      "Hit the green Calculate Z₀ button. Z₀ appears as a big emerald value in the Results panel. Diff-pair and 3-wire geometries get their own kind-aware result cards.",
  },
  {
    title: "5. See the field",
    body:
      "V / E / D / T tabs in the Results panel render the actual field plot via the bitmap solver. atlc2 keystrokes work — press V or E with the page focused. Press the small ↓ next to the tabs to download the PNG.",
  },
  {
    title: "6. Sweep & export",
    body:
      "The Sweep section in the Results panel runs frequency or geometry sweeps. After a frequency sweep, click ↓ .s2p to download a Touchstone file. Click ↓ JSON in the Results header for a full design snapshot.",
  },
];

export function Tour() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setSeen(window.localStorage.getItem(STORAGE_KEY) === "1");
  }, []);

  function close() {
    setOpen(false);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, "1");
    }
    setSeen(true);
  }

  return (
    <>
      <button
        onClick={() => {
          setStep(0);
          setOpen(true);
        }}
        title="Quick walk-through of the GUI"
        className="text-xs text-slate-400 hover:text-emerald-400 px-2 py-0.5 rounded border border-navy-700 hover:border-emerald-500"
      >
        {seen ? "Tour ✓" : "★ Tour"}
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6">
          <div className="bg-navy-950 border border-navy-700 rounded-lg max-w-md w-full p-5 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-slate-500">
                Step {step + 1} of {STEPS.length}
              </span>
              <button
                onClick={close}
                aria-label="close tour"
                className="text-slate-400 hover:text-slate-100"
              >
                ✕
              </button>
            </div>

            <h2 className="text-lg font-semibold text-emerald-300">{STEPS[step].title}</h2>
            <p className="text-sm text-slate-300 leading-relaxed">{STEPS[step].body}</p>

            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                disabled={step === 0}
                className="text-sm text-slate-400 disabled:text-slate-700 hover:text-slate-100"
              >
                ← Back
              </button>
              <div className="flex gap-1">
                {STEPS.map((_, i) => (
                  <span
                    key={i}
                    className={
                      "w-1.5 h-1.5 rounded-full " +
                      (i === step ? "bg-emerald-400" : "bg-slate-700")
                    }
                  />
                ))}
              </div>
              {step < STEPS.length - 1 ? (
                <button
                  onClick={() => setStep((s) => s + 1)}
                  className="text-sm bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded"
                >
                  Next →
                </button>
              ) : (
                <button
                  onClick={close}
                  className="text-sm bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1 rounded"
                >
                  Got it
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
