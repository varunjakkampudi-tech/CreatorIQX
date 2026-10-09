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
