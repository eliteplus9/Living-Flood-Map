import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const directory = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: resolve(directory),
  plugins: [react()],
  publicDir: "public",
  build: {
    outDir: resolve(directory, "../dist"),
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8787" },
  },
});
