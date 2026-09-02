import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// `globals: true` is not set in vitest.config.ts, so React Testing
// Library's own auto-cleanup (which detects a global `afterEach`) never
// registers - every multi-test file otherwise leaks a mounted tree from one
// test into the next.
afterEach(cleanup);
