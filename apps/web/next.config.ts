import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

/**
 * API base URL for the `/api` rewrite. Defaults to the local API from
 * `infra/compose/docker-compose.yml` (P0-020) so `pnpm dev` works on a
 * single origin without extra setup (P0-022 one-command setup).
 */
const apiOrigin = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  typedRoutes: true,
  // Minimal self-contained server bundle (.next/standalone) for the
  // production Docker image (P0-021): copying it plus .next/static and
  // public/ into the final stage avoids shipping full node_modules.
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
};

const withNextIntl = createNextIntlPlugin();

export default withNextIntl(nextConfig);
