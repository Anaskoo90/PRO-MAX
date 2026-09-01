import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// vite.config.ts intentionally doesn't set test.globals, so RTL's own
// auto-cleanup (which detects the framework via globals) never fires —
// without this, DOM nodes from one test in a file leak into the next,
// producing "found multiple elements" failures in later tests.
afterEach(() => {
  cleanup();
});
