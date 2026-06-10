import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#09090B",
          panel: "#111113",
          elevated: "#18181B",
        },
        border: {
          DEFAULT: "#232326",
          default: "#232326",
          strong: "#2E2E33",
        },
        text: {
          primary: "#FAFAFA",
          muted: "#A1A1AA",
          subtle: "#71717A",
        },
        accent: {
          DEFAULT: "#3B82F6",
          hover: "#2563EB",
        },
        state: {
          success: "#10B981",
          warning: "#F59E0B",
          error: "#EF4444",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      fontSize: {
        tiny: ["11px", "1.2"],
        xs: ["12px", "1.3"],
        sm: ["13px", "1.4"],
        base: ["14px", "1.5"],
        "base-lg": ["15px", "1.5"],
        lg: ["16px", "1.5"],
      },
    },
  },
  plugins: [],
} satisfies Config;
