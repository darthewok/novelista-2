import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: { alias: { "@": "/src" } },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } }, // dev only
  build: { outDir: "dist" },
});
