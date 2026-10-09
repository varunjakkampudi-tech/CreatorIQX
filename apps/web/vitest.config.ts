import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Vitest + Testing Library config for the design-system primitives
 * (P0-083). Unit tests live next to the component they test
 * (`button.test.tsx` beside `button.tsx`), separate from the Playwright
 * end-to-end tests in `tests/e2e` (playwright.config.ts), which this
 * config's `exclude` keeps out of Vitest's run.
 *
 * Vite doesn't read tsconfig's `paths` on its own, so the `@/*` alias
 * (tsconfig.json) is restated here - without it, Vitest's own Vite
 * instance can't resolve `@/lib/utils` from the primitives.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    exclude: ["**/node_modules/**", "tests/e2e/**"],
  },
});
