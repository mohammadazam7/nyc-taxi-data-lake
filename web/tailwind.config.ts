import type { Config } from "tailwindcss";
import { atlas } from "./src/atlas/tokens";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: atlas.color,
      fontFamily: { sans: atlas.font.sans },
      boxShadow: { panel: "0 18px 50px -24px rgba(0, 0, 0, 0.8)" },
      borderRadius: { panel: "14px" },
    },
  },
  plugins: [],
} satisfies Config;
