import { defineConfig } from "@playwright/test";

/**
 * Separate Playwright config for P0-083's accessibility gate: it serves
 * the static Storybook build (not the Next.js app) and scans every story
 * with axe-core (tests/e2e/a11y.spec.ts). Kept apart from
 * playwright.config.ts so the two webServers (Next.js vs. a static file
 * server over storybook-static) never compete for the same port.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "a11y.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:6007",
  },
  webServer: {
    command:
      "pnpm run build-storybook && pnpm exec http-server storybook-static -p 6007 -s",
    url: "http://127.0.0.1:6007",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
