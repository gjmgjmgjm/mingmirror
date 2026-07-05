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
      },
      fontFamily: {
        serif: ["'Noto Serif SC'", "serif"],
        display: ["'Zhi Mang Xing'", "cursive"],
      },
    },
  },
  plugins: [],
}
