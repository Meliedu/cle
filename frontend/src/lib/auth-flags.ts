/**
 * Where email + password auth is offered.
 *
 * Production (`cle-meli.hkust.edu.hk`) is HKUST-SSO-only. The credential path
 * exists only as a dev convenience — local demo accounts and the Clerk-hash
 * migration parity — so it is kept on the dev domain (`cle-meli-dev`) and local
 * development but rejected on production.
 *
 * The prod and dev domains are served by a SINGLE Vercel deployment (same build
 * and env vars, distinguished only by hostname), so a build-time flag can't
 * tell them apart — it would apply to both. The only reliable discriminator is
 * the request host at runtime. This helper is used by both the client
 * sign-in/up forms (`window.location.hostname`) and the server-side Better Auth
 * before-hook (`Host` header), so the two never disagree.
 *
 * Fail-closed: only the hosts listed here get email/password; every other host
 * — production and anything unexpected — is SSO-only.
 */
const EMAIL_PASSWORD_HOSTS: ReadonlySet<string> = new Set([
  "cle-meli-dev.hkust.edu.hk",
  "localhost",
  "127.0.0.1",
]);

/** True when `host` (with or without a port) may use email/password auth. */
export function isEmailPasswordHost(host: string | null | undefined): boolean {
  if (!host) return false;
  const hostname = host.split(":")[0].trim().toLowerCase();
  return EMAIL_PASSWORD_HOSTS.has(hostname);
}
