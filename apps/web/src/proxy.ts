import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Per-request Content Security Policy with a nonce (spec section 10, "Web
 * protection"; P0-082). A fresh nonce is generated on every request and
 * placed both in the CSP header (`script-src 'self' 'nonce-<value>'`) and in
 * a custom `x-nonce` request header, which `app/layout.tsx` reads via
 * `headers()` to pass to any script that needs one. Next.js auto-applies the
 * same nonce to the scripts it injects (its own runtime and page bundles) by
 * parsing the nonce back out of the CSP header, so most pages need no extra
 * wiring; see https://nextjs.org/docs/app/guides/content-security-policy.
 *
 * Nonce-based CSP requires dynamic rendering (a static page has no request
 * to generate a nonce for), so every page under this proxy's matcher opts
 * into dynamic rendering (see RootLayout and page.tsx).
 *
 * `strict-dynamic` plus a nonce (rather than an allow-list of origins) means
 * only scripts carrying the nonce - or scripts loaded by one of them - can
 * run, so an attacker who injects markup without the nonce cannot execute
 * script even via an otherwise-trusted CDN origin.
 */
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";

  const cspHeader = `
    default-src 'self';
    script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""};
    style-src 'self' 'nonce-${nonce}'${isDev ? " 'unsafe-inline'" : ""};
    img-src 'self' blob: data:;
    font-src 'self';
    connect-src 'self';
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-ancestors 'none';
    upgrade-insecure-requests;
  `
    .replace(/\s{2,}/g, " ")
    .trim();

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("content-security-policy", cspHeader);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("content-security-policy", cspHeader);
  response.headers.set("x-content-type-options", "nosniff");
  response.headers.set("x-frame-options", "DENY");
  response.headers.set("referrer-policy", "no-referrer");
  response.headers.set("cross-origin-opener-policy", "same-origin");
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
