/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f9f8f5",
          100: "#f4f1ea",
          200: "#e8e3d8",
          300: "#d1c9b8",
          400: "#a89e8a",
          500: "#7a746a",
          600: "#4a453d",
          700: "#2c2824",
          800: "#1f1c19",
          900: "#161412",
        },
        vermilion: {
          DEFAULT: "#c53d2f",
          light: "#d44a3a",
          dark: "#9e2f23",
        },
        gold: {
          DEFAULT: "#c9a227",
          light: "#d4b04a",
          dark: "#9e7f1f",
        },
        jade: "#5a8f7b",
        // Semantic design tokens
        surface: {
          DEFAULT: "rgba(255, 255, 255, 0.8)",
          elevated: "rgba(255, 255, 255, 0.92)",
          sunken: "rgba(244, 241, 234, 0.5)",
          dark: {
            DEFAULT: "rgba(31, 28, 25, 0.8)",
            elevated: "rgba(44, 40, 36, 0.92)",
            sunken: "rgba(22, 20, 18, 0.5)",
          },
        },
        border: {
          subtle: "rgba(209, 201, 184, 0.2)",
          DEFAULT: "rgba(209, 201, 184, 0.4)",
          strong: "rgba(209, 201, 184, 0.6)",
          dark: {
            subtle: "rgba(74, 69, 61, 0.2)",
            DEFAULT: "rgba(74, 69, 61, 0.4)",
            strong: "rgba(74, 69, 61, 0.6)",
          },
        },
      },
      fontFamily: {
        serif: ["'Noto Serif SC'", "serif"],
        display: ["'Zhi Mang Xing'", "cursive"],
      },
      boxShadow: {
        panel: "0 10px 30px rgba(44, 40, 36, 0.08)",
        "panel-hover": "0 18px 40px rgba(44, 40, 36, 0.12)",
        "panel-dark": "0 10px 30px rgba(0, 0, 0, 0.25)",
        "panel-dark-hover": "0 18px 40px rgba(0, 0, 0, 0.35)",
        glow: "0 0 20px rgba(197, 61, 47, 0.15)",
        "glow-lg": "0 0 30px rgba(197, 61, 47, 0.22)",
      },
      spacing: {
        18: "4.5rem",
        22: "5.5rem",
        30: "7.5rem",
      },
      borderRadius: {
        "2.5xl": "1.25rem",
      },
      transitionDuration: {
        400: "400ms",
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out forwards",
        "page-enter": "page-enter 0.35s ease-out forwards",
        "bg-drift": "bg-drift 20s ease-in-out infinite alternate",
        "cloud-drift": "cloud-drift 60s linear infinite",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "page-enter": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "bg-drift": {
          "0%": { transform: "translate(0, 0) scale(1)", filter: "hue-rotate(0deg)" },
          "33%": { transform: "translate(2%, -1%) scale(1.02)" },
          "66%": { transform: "translate(-1%, 2%) scale(1.01)" },
          "100%": { transform: "translate(0, 0) scale(1)", filter: "hue-rotate(6deg)" },
        },
        "cloud-drift": {
          "0%": { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "180px 180px" },
        },
      },
    },
  },
  plugins: [],
}
