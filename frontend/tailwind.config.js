/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["'JetBrains Mono'", "'SF Mono'", "monospace"],
      },
      colors: {
        bg: "#0a0a0a",
        card: "#141414",
        border: "#262626",
      },
    },
  },
  plugins: [],
};
