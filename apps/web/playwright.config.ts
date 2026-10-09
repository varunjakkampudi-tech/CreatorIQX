import { defineConfig } from "@playwright/test";

/**
 * Playwright config for P0-082's CSP acceptance test. `webServer` lets
 * Playwright itself start and stop `next build && next start` and wait for
 * it to be ready, rather than a hand-backgrounded process - the backgrounded
 * `next start &` approach hung a CI step past its timeout in P0-080 (see
 * docs/PROGRESS.md), so this sidesteps that failure mode entirely rather
 * than repeating it.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:3100",
  },
  webServer: {
    // `next start` reads PORT from the environment; passing `-- --port`
    // through `pnpm run` double-forwarded the "--" itself in CI (pnpm
    // 12.10.1), producing `next start -- --port 3100` and a "no such
    // directory: --port" error, so PORT avoids the arg-forwarding path
    // entirely instead of chasing that quoting.
    command: "pnpm run build && pnpm run start",
    url: "http://127.0.0.1:3100",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { PORT: "3100" },
  },
});
