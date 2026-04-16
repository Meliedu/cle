import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest } from "next/server";

const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)"]);

const isDev = process.env.NODE_ENV !== "production";

const apiOrigin = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return "";
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
})();

const wsOrigin = apiOrigin.replace(/^https?:/, (match) =>
  match === "https:" ? "wss:" : "ws:",
);

/**
 * Build a per-request CSP header string using the supplied nonce.
 *
 * Nonces replace `'unsafe-inline'` on script-src so injected inline scripts
 * cannot execute. `'strict-dynamic'` lets nonced scripts load additional
 * scripts without separately allow-listing every CDN; the Clerk SDK loads
 * its own chunks this way.
 *
 * In development, Turbopack and React DevTools rely on `eval`, so we allow
 * `'unsafe-eval'` and inline styles. Production stays strict.
 */
function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""} https://*.clerk.accounts.dev https://*.clerk.com https://challenges.cloudflare.com`,
    `style-src 'self' ${isDev ? "'unsafe-inline'" : `'nonce-${nonce}' 'unsafe-inline'`} https://fonts.googleapis.com`,
    "img-src 'self' data: blob: https:",
    "font-src 'self' https://fonts.gstatic.com data:",
    `connect-src 'self' https://*.clerk.accounts.dev https://*.clerk.com https://api.clerk.com${apiOrigin ? ` ${apiOrigin}` : ""}${wsOrigin ? ` ${wsOrigin}` : ""}`,
    "frame-src 'self' https://challenges.cloudflare.com https://*.clerk.accounts.dev",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ];
  return directives.join("; ");
}

/**
 * Generate a base64 nonce per request. Must be unpredictable so an attacker
 * cannot guess a value that would be accepted for a subsequent inline
 * script injection.
 */
function generateNonce(): string {
  // crypto.randomUUID is available in the edge runtime Next.js uses.
  const uuid = crypto.randomUUID();
  // Strip hyphens and base64-encode for CSP-compatibility.
  const bytes = new TextEncoder().encode(uuid.replace(/-/g, ""));
  return btoa(String.fromCharCode(...bytes));
}

/**
 * Apply the per-request CSP and propagate the nonce downstream via the
 * `x-nonce` request header so that:
 *   - Next.js reads the CSP header and auto-attaches the nonce to its own
 *     framework/page scripts during SSR.
 *   - Clerk's `DynamicClerkScripts` reads the `X-Nonce` header and attaches
 *     the nonce to clerk-js script tags.
 */
function withCspHeaders(request: NextRequest): NextResponse {
  const nonce = generateNonce();
  const csp = buildCsp(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect();
  }
  return withCspHeaders(request);
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
