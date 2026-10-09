import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Vitest + Testing Library config for the design-system primitives
 * (P0-083). Unit tests live next to the component they test
 * (`button.test.tsx` beside `button.tsx`), separate from the Playwright
 * end-to-end tests in `tests/e2e` (playwright.config.ts), which this
 * config's `exclude` keeps out of Vitest's run.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    exclude: ["**/node_modules/**", "tests/e2e/**"],
  },
});
