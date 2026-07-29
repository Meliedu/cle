/**
 * The one predicate that decides whether a server-supplied string may be shown
 * to a user.
 *
 * This lives in its own module, importing nothing, because BOTH ends of the
 * error path need it and they would otherwise form an import cycle:
 * `lib/api.ts` sanitises at the fetch boundary, and
 * `lib/contracts/safe-error.ts` imports `ApiError` from `lib/api.ts`.
 *
 * Placing the check at the boundary matters more than placing it at each render
 * site. The product renders `error.message` in roughly thirty components; a
 * guard applied per-component is one forgotten call away from re-leaking, while
 * a guard in `apiFetch` covers every present and future caller.
 */

/**
 * Patterns that mark a string as implementation detail rather than user copy.
 * A match means the string is discarded in favour of generic safe copy.
 */
const INTERNAL_PATTERNS: readonly RegExp[] = [
  // Python/JS exception class names: "AttributeError:", "TypeError:"
  /\b[A-Z][A-Za-z]*(?:Error|Exception|Warning)\b\s*:/,
  // Attribute access and object reprs
  /\bobject has no attribute\b/i,
  /\b__[a-z_]+__\b/,
  // Stack frames and source paths
  /\bTraceback \(most recent call last\)/i,
  /\bFile "[^"]+", line \d+/,
  /(?:^|[\s(])\/(?:usr|app|home|var|opt|tmp)\//,
  /[A-Za-z]:\\\\?(?:Users|Program Files)\\/i,
  // Module paths, provider and library names. The trailing class allows
  // digits so versioned names ("boto3") match, and `r2`/`s3` are included
  // because object-storage errors name the bucket service directly.
  /\bapp\.(?:services|api|models|schemas)\.[a-z_]+/,
  /\b(?:llm|openrouter|openai|anthropic|r2|s3|boto|asyncpg|sqlalchemy|pydantic|docling|whisper)[_.a-z0-9]*\b/i,
  // Connection strings, buckets, object keys, correlation ids
  /\b[a-z][a-z0-9+\-.]*:\/\/\S+/i,
  /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/i,
  // SQL fragments
  /\b(?:SELECT|INSERT INTO|UPDATE|DELETE FROM|CONSTRAINT|psql)\b/,
  // HTTP plumbing
  /\bHTTP \d{3}\b/,
  /\brequest[_ ]id\b/i,
];

/**
 * True when a candidate string is safe to show a user.
 *
 * Deliberately conservative: an unrecognised-but-harmless string that trips a
 * pattern is replaced by generic copy, which is a worse message but never a
 * disclosure. The reverse trade would not be acceptable.
 */
export function isUserSafeText(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.length === 0) return false;
  // Anything long enough to be a dumped payload is not user copy.
  if (trimmed.length > 240) return false;
  return !INTERNAL_PATTERNS.some((pattern) => pattern.test(trimmed));
}

/**
 * Return `value` when it is safe to render, otherwise `fallback`.
 *
 * Used at ingest points that hold a server string but have no typed code to
 * fall back to, such as the background-job status payload.
 */
export function userSafeOr(
  value: string | null | undefined,
  fallback: string
): string {
  return value && isUserSafeText(value) ? value : fallback;
}
