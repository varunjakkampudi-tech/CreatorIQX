import { headers } from "next/headers";

/**
 * Test-only fixture for P0-082's CSP acceptance test
 * (tests/e2e/csp.spec.ts), not a product screen (P0-090 untouched).
 *
 * Playwright's `page.evaluate`/`addScriptTag` inject script through the
 * DevTools Protocol, which Chromium runs in a privileged context that
 * bypasses the page's CSP - useful for driving a page, useless for
 * proving the browser actually enforces it. This route instead renders
 * two genuine inline `<script>` elements server-side: one carrying the
 * request's nonce (allowed), one without (must be blocked), so the test
 * observes real CSP enforcement on real HTML rather than CDP-injected
 * script.
 */
export default async function CspCheckPage() {
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <main>
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{
          __html: "window.__cspCheckTrustedRan = true;",
        }}
      />
      <script
        dangerouslySetInnerHTML={{
          __html: "window.__cspCheckUntrustedRan = true;",
        }}
      />
    </main>
  );
}
