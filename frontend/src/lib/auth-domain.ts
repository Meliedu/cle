// Email-domain → role mapping. Mirrors backend `detect_role_from_email` in
// `app/services/auth.py` so the Better Auth signup hook rejects disallowed
// domains client-side before the user ever hits the backend.

export type Role = "student" | "instructor";

const DOMAIN_ROLES: Record<string, Role> = {
  "ust.hk": "instructor",
  "connect.ust.hk": "student",
};

export const ALLOWED_DOMAINS = Object.keys(DOMAIN_ROLES);

export class DisallowedEmailDomainError extends Error {
  constructor(public readonly domain: string) {
    super(`Email domain ${domain} is not allowed`);
    this.name = "DisallowedEmailDomainError";
  }
}

export function detectRoleFromEmail(email: string): Role {
  const trimmed = email.trim().toLowerCase();
  const at = trimmed.lastIndexOf("@");
  if (at === -1) {
    throw new DisallowedEmailDomainError("(no @)");
  }
  const domain = trimmed.slice(at + 1);
  const role = DOMAIN_ROLES[domain];
  if (!role) {
    throw new DisallowedEmailDomainError(domain);
  }
  return role;
}
