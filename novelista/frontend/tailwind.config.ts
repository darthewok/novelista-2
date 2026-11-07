import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        serif: ["Literata", "Georgia", "serif"],
      },
      colors: {
        accent: {
          DEFAULT: "#6366f1",
          hover: "#4f46e5",
        },
      },
      borderRadius: { DEFAULT: "0.5rem" },
    },
  },
  plugins: [],
} satisfies Config;
