import { expect, test } from "@playwright/test";

/**
 * P0-082 acceptance test: "CSP header present with nonce; inline script
 * without nonce blocked." proxy.ts (apps/web/src/proxy.ts) generates a
 * fresh nonce per request and sets it on both the CSP header and any
 * script Next.js itself injects; nothing else gets to run inline.
 */
test.describe("Content Security Policy (P0-082)", () => {
  test("the response carries a per-request CSP with a nonce", async ({
    page,
  }) => {
    const response = await page.goto("/");
    const csp = response?.headers()["content-security-policy"];
    expect(csp).toBeTruthy();
    expect(csp).toMatch(/script-src[^;]*'nonce-[A-Za-z0-9+/=]+'/);
    expect(csp).toContain("strict-dynamic");
    expect(csp).toContain("frame-ancestors 'none'");
  });

  test("two requests get two different nonces", async ({ page }) => {
    const first = await page.goto("/");
    const firstCsp = first?.headers()["content-security-policy"] ?? "";
    const second = await page.goto("/");
    const secondCsp = second?.headers()["content-security-policy"] ?? "";
    expect(firstCsp).not.toBe("");
    expect(firstCsp).not.toBe(secondCsp);
  });

  test("an inline script without the nonce does not run, but one with it does", async ({
    page,
  }) => {
    // /csp-check (a tests/e2e fixture only, not a product screen) renders
    // two genuine server-side inline scripts: one carrying the request's
    // nonce, one without. Driving this through Playwright's own
    // evaluate/addScriptTag would prove nothing - those inject through the
    // DevTools Protocol, which Chromium runs in a context that bypasses
    // the page's CSP - so this checks real, browser-parsed HTML instead.
    await page.goto("/csp-check");

    const trustedRan = await page.evaluate(
      // @ts-expect-error -- test-only global, not part of the app
      () => window.__cspCheckTrustedRan,
    );
    const untrustedRan = await page.evaluate(
      // @ts-expect-error -- test-only global, not part of the app
      () => window.__cspCheckUntrustedRan,
    );

    expect(trustedRan).toBe(true);
    expect(untrustedRan).toBeUndefined();
  });
});
