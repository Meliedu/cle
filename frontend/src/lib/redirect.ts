/**
 * Sanitize a user-supplied post-auth redirect target.
 *
 * Why parser-based instead of a regex: the navigation sink
 * (`router.push` → WHATWG URL) strips TAB/LF/CR *anywhere* in the string
 * before parsing and treats "\" as "/", so any character-level guard checks
 * a DIFFERENT string than the one the router ultimately resolves — e.g.
 * "/\t/evil.com" passes a "second char isn't a slash" regex but resolves to
 * https://evil.com. Validating with the same primitive as the sink closes
 * that parser-mismatch class entirely: we parse against a sentinel base and
 * only return the parser's own normalized output (control chars already
 * stripped, backslashes already folded), never the raw input.
 *
 * Rejected (→ /dashboard):
 * - absolute URLs ("https://evil.com") — origin differs from the sentinel
 * - scheme URLs ("javascript:alert(1)") — non-hierarchical, origin "null"
 * - protocol-relative ("//evil.com", "/\evil.com", "/\t/evil.com", …) —
 *   all normalize onto a different origin
 * - paths that normalize to "//..." (e.g. "/.//evil.com") — would be
 *   protocol-relative when the returned string is navigated
 * - null / empty / unparseable
 */
export const DEFAULT_REDIRECT = "/dashboard";

const SENTINEL_ORIGIN = "https://x.invalid";

export function sanitizeRedirect(raw: string | null): string {
  if (!raw) return DEFAULT_REDIRECT;
  try {
    const url = new URL(raw, SENTINEL_ORIGIN);
    if (url.origin === SENTINEL_ORIGIN && !url.pathname.startsWith("//")) {
      // Normalized by the parser — safe to hand to router.push.
      return url.pathname + url.search + url.hash;
    }
  } catch {
    /* unparseable — fall through to the default */
  }
  return DEFAULT_REDIRECT;
}
