import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The build output is gitignored into the package (docs/adr/0002); dev
// proxies /api to the FastAPI app so the client never needs a base URL
// baked in, in dev or in the built bundle - README.md's "one command" run
// serves both from the same origin (uvicorn's StaticFiles mount).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
