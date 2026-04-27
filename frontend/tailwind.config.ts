import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

const phoenixPlugin = plugin(({ addUtilities }) => {
  addUtilities({
    /* ── glass system ─────────────────────────────────────────── */
    ".glass-soft": {
      background:
        "var(--glass-grad-1), linear-gradient(180deg, rgba(15,17,21,0.78) 0%, rgba(10,12,16,0.72) 100%)",
      backdropFilter: "var(--blur-soft)",
      WebkitBackdropFilter: "var(--blur-soft)",
      boxShadow: "var(--bevel-soft)",
    },
    ".glass-card": {
      background:
        "var(--glass-grad-2), linear-gradient(180deg, rgba(17,19,23,0.72) 0%, rgba(13,15,18,0.68) 100%)",
      backdropFilter: "var(--blur-glass)",
      WebkitBackdropFilter: "var(--blur-glass)",
      boxShadow: "var(--bevel-full), var(--shadow-card)",
      border: "1px solid var(--card-border)",
    },
    ".glass-strong": {
      background:
        "var(--glass-grad-3), linear-gradient(180deg, rgba(20,23,28,0.78) 0%, rgba(13,15,18,0.74) 100%)",
      backdropFilter: "var(--blur-strong)",
      WebkitBackdropFilter: "var(--blur-strong)",
      boxShadow: "var(--bevel-strong), var(--shadow-card-deep)",
    },
    ".edge-glass": {
      boxShadow: "var(--edge-glass-top), var(--edge-glass-bottom)",
    },

    /* ── tier colors (frame + glow) ───────────────────────────── */
    ".tier-r": {
      "--tier-color": "var(--tier-r-color)",
      "--tier-border": "var(--tier-r-border)",
      "--tier-glow": "transparent",
    },
    ".tier-b": {
      "--tier-color": "var(--tier-b-color)",
      "--tier-border": "var(--tier-b-border)",
      "--tier-glow": "var(--tier-b-glow)",
    },
    ".tier-a": {
      "--tier-color": "var(--tier-a-color)",
      "--tier-border": "var(--tier-a-border)",
      "--tier-glow": "var(--tier-a-glow)",
    },
    ".tier-ap": {
      "--tier-color": "var(--tier-ap-color)",
      "--tier-border": "var(--tier-ap-border)",
      "--tier-glow": "var(--tier-ap-glow)",
    },
    ".tier-s": {
      "--tier-color": "var(--tier-s-color)",
      "--tier-border": "var(--tier-s-border)",
      "--tier-glow": "var(--tier-s-glow)",
    },
    ".tier-sp": {
      "--tier-color": "var(--tier-sp-color)",
      "--tier-border": "var(--tier-sp-border)",
      "--tier-glow": "var(--tier-sp-glow)",
    },

    /* ── bookmark clip-path (lengüeta marca-páginas) ──────────── */
    ".bookmark-shape": {
      clipPath: "polygon(0 0, 100% 0, 100% 70%, 92% 78%, 50% 100%, 8% 78%, 0 70%)",
    },

    /* ── iridescent panels (rotación Houdini) ─────────────────── */
    ".iridescent-bg": {
      background:
        "conic-gradient(from var(--iri-angle) at 50% 50%, #FF6A2C, #c4b5fd, #fdba74, #f9a8d4, #FF6A2C)",
      animation: "iri-rotate 11s linear infinite",
    },
    ".iridescent-pan": {
      backgroundSize: "200% 100%",
      animation: "iri-pan 9s linear infinite",
    },

    /* ── numeric / mono helpers ───────────────────────────────── */
    ".num-tabular": {
      fontFamily: "var(--font-mono)",
      fontVariantNumeric: "tabular-nums",
      letterSpacing: "-0.01em",
    },
  });
});

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        ui: ["Geist", "Söhne", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        bg: {
          DEFAULT: "var(--bg)",
          1: "var(--bg-elev-1)",
          2: "var(--bg-elev-2)",
          3: "var(--bg-elev-3)",
          4: "var(--bg-elev-4)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          2: "var(--accent-2)",
          deep: "var(--accent-deep)",
          darker: "var(--accent-darker)",
        },
        ok: "var(--ok)",
        warn: "var(--warn)",
        err: "var(--err)",
        bull: "var(--bull)",
        bear: "var(--bear)",
        text: {
          100: "var(--t-100)",
          90: "var(--t-90)",
          75: "var(--t-75)",
          55: "var(--t-55)",
          38: "var(--t-38)",
          22: "var(--t-22)",
          12: "var(--t-12)",
        },
      },
      borderRadius: {
        sm: "var(--r-sm)",
        DEFAULT: "var(--r)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        card: "var(--r-card)",
        pill: "var(--r-pill)",
      },
      transitionTimingFunction: {
        phoenix: "cubic-bezier(0.4, 0, 0.2, 1)",
      },
    },
  },
  plugins: [phoenixPlugin],
} satisfies Config;
