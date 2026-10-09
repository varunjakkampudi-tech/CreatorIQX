import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

// Testing Library's automatic cleanup-after-each-test only self-registers
// when it finds a global `afterEach` (Jest-style globals). This project's
// vitest.config.ts doesn't turn on `test.globals`, so without this, every
// rendered component stayed in the DOM across tests in the same file and
// later tests failed with "found multiple elements" against the leftovers.
afterEach(() => {
  cleanup();
});
