import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    // Scoped to `src/` so the browser gate walk under `gate/` - a
    // Playwright spec, meaningless in jsdom - is never collected here.
    // `npm test` stays the standing UI gate and stays browser-free
    // (CLAUDE.md); the walk is `npm run gate`.
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
