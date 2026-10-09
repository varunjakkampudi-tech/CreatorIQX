import type { Metadata } from "next";
import type { ReactNode } from "react";
import productConfig from "@creatoriqx/config/product.json" with { type: "json" };
import "./globals.css";

export const metadata: Metadata = {
  title: productConfig.productName,
  description: productConfig.tagline,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
