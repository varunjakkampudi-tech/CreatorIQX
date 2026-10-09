import type { Metadata } from "next";
import type { ReactNode } from "react";
import { NextIntlClientProvider } from "next-intl";
import productConfig from "@creatoriqx/config/product.json" with { type: "json" };
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: productConfig.productName,
  description: productConfig.tagline,
};

// Nonce-based CSP (proxy.ts, P0-082) only exists per-request, so every page
// under the root layout must render dynamically - a statically generated
// page would have no request to read a nonce from.
export const dynamic = "force-dynamic";

// Any future page or layout that needs to pass a nonce to a <Script> or
// third-party embed (spec section 10) reads it with
// `(await headers()).get("x-nonce")` - see proxy.ts for where it's set.
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
