import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("..", import.meta.url)) } },
  publicDir: false,
  build: { outDir: "../../tmp/stl4-workspace-proposals-20261107/site", emptyOutDir: false },
});
