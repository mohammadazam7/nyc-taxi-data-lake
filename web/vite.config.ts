/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served from https://<user>.github.io/nyc-taxi-data-lake/, so assets need that base.
export default defineConfig({
  base: process.env.PAGES_BASE ?? "./",
  plugins: [react()],
  build: {
    target: "es2022",
    sourcemap: true,
    rollupOptions: {
      output: {
        // three.js and the R3F stack load as their own chunk after the shell paints.
        manualChunks: { three: ["three", "@react-three/fiber", "@react-three/drei"] },
      },
    },
  },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts?(x)"] },
});
