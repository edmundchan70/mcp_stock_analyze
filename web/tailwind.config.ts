import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Charcoal neutral workspace (calm dark terminal).
        ink: {
          950: "#0b0c0e",
          900: "#121316",
          850: "#16181c",
          800: "#1b1d22",
          750: "#202329",
          700: "#262a31",
          600: "#32363e",
          500: "#3f444e",
        },
        // Warm amber accent — actions + active filters only.
        accent: {
          DEFAULT: "#e0a33c",
          300: "#eec476",
          400: "#e8b35c",
          500: "#e0a33c",
          600: "#c98f2d",
          700: "#a97824",
        },
        // Semantic up/down — strictly green/red for price direction.
        up: {
          DEFAULT: "#2fbf9a",
          500: "#34c9a3",
          600: "#26a68a",
        },
        down: {
          DEFAULT: "#e05c5c",
          500: "#e76a6a",
          600: "#c94a4a",
        },
      },
      fontFamily: {
        sans: ['"Instrument Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", "1rem"],
      },
    },
  },
  plugins: [],
};

export default config;
