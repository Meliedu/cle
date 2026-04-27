import { NextResponse, type NextRequest } from "next/server";
import { headers } from "next/headers";

import { auth } from "@/lib/auth";

const PUBLIC_PATHS = ["/", "/sign-in", "/sign-up", "/forgot-password", "/reset-password", "/verify-email"];

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
 * scripts without separately allow-listing every CDN.
 *
 * In development, Turbopack and React DevTools rely on `eval`, so we allow
 * `'unsafe-eval'` and inline styles. Production stays strict.
 *
 * Connect-src includes login.microsoftonline.com because the Microsoft OAuth
 * sign-in flow round-trips through there. Frame-src allows it for the
 * embedded login screen.
 */
function buildCsp(nonce: string): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https:",
    "font-src 'self' https://fonts.gstatic.com data:",
    `connect-src 'self' https://login.microsoftonline.com https://graph.microsoft.com${apiOrigin ? ` ${apiOrigin}` : ""}${wsOrigin ? ` ${wsOrigin}` : ""}`,
    "frame-src 'self' https://login.microsoftonline.com",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self' https://login.microsoftonline.com",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ];
  return directives.join("; ");
}

function generateNonce(): string {
  const uuid = crypto.randomUUID();
  const bytes = new TextEncoder().encode(uuid.replace(/-/g, ""));
  return btoa(String.fromCharCode(...bytes));
}

function attachCsp(request: NextRequest, response: NextResponse): NextResponse {
  const nonce = generateNonce();
  const csp = buildCsp(nonce);
  // The layout reads x-nonce off the incoming request to stamp the nonce on
  // SSR-emitted scripts. Set it on the *request* headers Next.js will see.
  request.headers.set("x-nonce", nonce);
  request.headers.set("Content-Security-Policy", csp);
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

function isPublicPath(pathname: string): boolean {
  if (PUBLIC_PATHS.includes(pathname)) return true;
  // The Better Auth catch-all and our /api/internal routes must remain
  // accessible without a session cookie (they have their own auth).
  if (pathname.startsWith("/api/auth/")) return true;
  return false;
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Skip auth check on public routes — still apply CSP.
  if (isPublicPath(pathname)) {
    return attachCsp(request, NextResponse.next({ request }));
  }

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("redirect", pathname);
    return attachCsp(request, NextResponse.redirect(url));
  }

  return attachCsp(request, NextResponse.next({ request }));
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
