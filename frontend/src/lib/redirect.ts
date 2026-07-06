/**
 * Sanitize a user-supplied post-auth redirect target.
 *
 * Only same-origin, path-absolute URLs are allowed. Everything else falls
 * back to /dashboard:
 *
 * - absolute URLs ("https://evil.com") — cross-origin
 * - scheme URLs ("javascript:alert(1)") — XSS vector
 * - protocol-relative ("//evil.com") — resolves cross-origin
 * - backslash variants ("/\evil.com") — WHATWG URL parsing normalizes "\"
 *   to "/", so "/\evil.com" becomes "//evil.com" and escapes the origin
 * - null / empty — nothing requested
 */
export const DEFAULT_REDIRECT = "/dashboard";

export function sanitizeRedirect(raw: string | null): string {
  if (!raw) return DEFAULT_REDIRECT;
  // Must be path-absolute ("/...") and the second character must not be
  // another separator ("/" or "\") — that's the protocol-relative escape.
  if (raw.startsWith("/") && !/^\/[/\\]/.test(raw)) return raw;
  return DEFAULT_REDIRECT;
}
