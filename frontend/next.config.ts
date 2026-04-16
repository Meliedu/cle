import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// CSP is emitted per-request from `src/proxy.ts` so each response carries a
// fresh nonce. Keeping it in next.config.ts as a static header would either
// force `'unsafe-inline'` (defeating XSS protection) or conflict with the
// nonce-bearing header set by the proxy. Only non-nonce security headers
// remain here.
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(self), geolocation=(), interest-cohort=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains; preload",
  },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

const withNextIntl = createNextIntlPlugin();
export default withNextIntl(nextConfig);
