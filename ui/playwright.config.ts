import { defineConfig } from "@playwright/test";

/**
 * The browser driver for the milestone gate walks (`docs/gates/`), and
 * nothing else.
 *
 * `CLAUDE.md` keeps this out of the standing gate on purpose: `npm test` is
 * vitest over jsdom and stays fast and browser-free, and this config is
 * reached only through `npm run gate`, which `scripts/gate-m3.sh` calls
 * with a server already up. There is no `webServer` block here for that
 * reason - the server a gate walk needs is not `vite dev` but a uvicorn
 * process over a *prepared* repository (seeded, normalized, rebuilt), and
 * the shell script owns that whole lifecycle.
 */
export default defineConfig({
  testDir: "./gate",
  // A gate walk is a sequence, not a suite: step 6 asks whether closing the
  // panel left the page where step 4 scrolled it to. Parallelism would make
  // that question meaningless.
  fullyParallel: false,
  workers: 1,
  // A gate that passes on the second try has not answered the question it
  // was asked. A flake here is a finding, so it is reported, not retried.
  retries: 0,
  // The whole walk runs against a three-record corpus; anything slower than
  // this is a symptom, not a slow machine.
  timeout: 30_000,
  use: {
    baseURL: process.env.MEMORIA_GATE_URL ?? "http://127.0.0.1:8123",
    // Fixed, and smaller than the page: "did I keep my place" is only a
    // real question on a page that scrolls, and a viewport tall enough to
    // show the whole entry would make step 6 pass vacuously.
    viewport: { width: 1280, height: 720 },
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});
