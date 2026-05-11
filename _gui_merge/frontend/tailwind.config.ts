import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // EDA studio palette: deep navy bg, teal accent, gold for warnings,
        // emerald-green for results.
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
        // atlc-style conductor accents (used by SVG diagrams + results)
        signal: "#dc2626",
        signalAlt: "#3b82f6",
        ground: "#16a34a",
        diel: "#fde68a",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 12px rgba(6, 182, 212, 0.35)",
        "glow-emerald": "0 0 12px rgba(16, 185, 129, 0.35)",
      },
      backgroundImage: {
        "header-gradient":
          "linear-gradient(90deg, #0a0e16 0%, #0f1623 50%, #1a2332 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
