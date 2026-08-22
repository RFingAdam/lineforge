import type { Config } from "tailwindcss";

/**
 * lineforge design tokens.
 *
 * Two layers, by intent:
 *   - Legacy palette (navy / teal / signal / ground / diel) kept verbatim for
 *     backwards-compat with components that haven't been migrated yet.
 *   - Flat **semantic tokens** (surface, border-subtle, accent, success, ...)
 *     so new components speak intent instead of raw hex. Tailwind v3 JIT
 *     doesn't support nested arbitrary keys in `extend.colors`, so semantic
 *     tokens are declared as flat top-level entries: e.g. `bg-surface`,
 *     `border-border-subtle`, `text-accent`.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // EDA studio palette. Retained for legacy class references.
        navy: {
          950: "#0a0e16",
          900: "#0f1623",
          800: "#1a2332",
          700: "#252e3f",
        },
        teal: {
          accent: "#06b6d4",
          glow: "#22d3ee",
        },
        signal: "#dc2626",
        signalAlt: "#3b82f6",
        ground: "#16a34a",
        diel: "#fde68a",

        // ── semantic tokens ────────────────────────────────────────────────
        canvas: "#0a0e16",
        surface: "#0f1623",
        "surface-raised": "#1a2332",
        "surface-overlay": "#252e3f",

        "border-subtle": "#1a2332",
        "border-strong": "#252e3f",

        accent: "#06b6d4",
        "accent-strong": "#22d3ee",

        success: "#10b981", // emerald-500
        warn: "#fbbf24", // amber-400
        danger: "#f43f5e", // rose-500
        info: "#38bdf8", // sky-400
      },
      fontFamily: {
        display: [
          "var(--font-display)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "var(--font-mono)",
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      boxShadow: {
        glow: "0 0 12px rgba(6, 182, 212, 0.35)",
        "glow-emerald": "0 0 12px rgba(16, 185, 129, 0.35)",
        card: "0 1px 2px 0 rgba(0,0,0,0.4), 0 1px 3px 0 rgba(0,0,0,0.6)",
        "card-hover":
          "0 2px 4px 0 rgba(0,0,0,0.5), 0 4px 8px -2px rgba(0,0,0,0.7)",
        panel:
          "0 2px 6px 0 rgba(0,0,0,0.5), 0 8px 24px -8px rgba(0,0,0,0.7)",
        modal:
          "0 10px 25px -5px rgba(0,0,0,0.8), 0 20px 50px -12px rgba(0,0,0,0.9)",
        topbar: "0 1px 0 0 rgba(0,0,0,0.6), 0 4px 12px -4px rgba(0,0,0,0.5)",
      },
      borderRadius: {
        xs: "0.25rem",
        sm: "0.375rem",
        md: "0.5rem",
        lg: "0.75rem",
      },
      backgroundImage: {
        "header-gradient":
          "linear-gradient(90deg, #0a0e16 0%, #0f1623 50%, #1a2332 100%)",
        "topbar-gradient":
          "linear-gradient(90deg, #0f1623 0%, #1a2332 50%, #0f1623 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
