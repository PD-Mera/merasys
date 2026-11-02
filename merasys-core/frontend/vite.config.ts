import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/agent": { target: "http://127.0.0.1:21707", changeOrigin: false },
      "/api": { target: "http://127.0.0.1:21707", changeOrigin: false },
      "/healthz": { target: "http://127.0.0.1:21707", changeOrigin: false },
    },
  },
});
