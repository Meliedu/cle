# Meli, Security Posture

This document records how Meli satisfies the HKUST ITSO **Minimum Security Standard**
(Application Systems and SaaS on Cloud) and the **Application Development Guidelines**.
It describes the controls that exist in the codebase today, organised by security
domain, with a requirement-by-requirement mapping at the end.

- **Data classification:** High-Risk. Meli stores student personal records (identity,
  enrolment, learning-performance data), which are protected by the Personal Data
  (Privacy) Ordinance, so the strictest column of the Minimum Security Standard applies.
- **Reporting a vulnerability:** email the maintainer and HKUST ITSO
  (`cchelp@ust.hk` / `seccomp@ust.hk`). Do not open a public issue for a security bug.

---

## 1. Authentication and identity

Meli authenticates through **HKUST OIDC (Microsoft Entra ID)** using the self-hosted
**Better Auth** library. This satisfies the ITSO requirement to integrate with
University authentication infrastructure rather than run a self-managed credential store.

- **Tenant-pinned, signature-verified OIDC.** Sign-in uses Microsoft's multi-tenant
  `/organizations/` endpoint so one application serves both staff (`@ust.hk`) and
  students (`@connect.ust.hk`), who reside in two separate Entra tenants. The
  `getUserInfo` step in `frontend/src/lib/auth.ts`:
  - selects the tenant from the id_token `tid`,
  - rejects any `tid` not in the HKUST tenant allow-list,
  - verifies the id_token signature against that tenant's JWKS, pinning the `issuer`,
    the `audience` (the application's own client id), and the signing algorithm.

  Only tokens minted by HKUST's own tenants are accepted; a claim such as `email` from
  any other tenant cannot be used to gain access.
- **Email-domain authorization on every sign-in.** `ust.hk` maps to instructor and
  `connect.ust.hk` to student; all other domains are refused. The gate runs both during
  the OIDC exchange and inside the user-creation hook, in the same transaction as the
  row insert, so a rejected sign-up leaves no orphaned identity.
- **Backend re-verification per request.** The FastAPI backend verifies the Better Auth
  JWT against the JWKS with the algorithm pinned to EdDSA only (preventing
  algorithm-confusion), re-derives the caller's role from the token on every request,
  and refuses any request whose domain is no longer allow-listed, so a revoked or
  domain-changed identity cannot continue on a cached session.
- **No self-managed credential path in production.** Email/password endpoints exist for
  the development host only and are refused on the production host by a fail-closed,
  per-request host gate. Required auth secrets (`BETTER_AUTH_SECRET`, the dashboard API
  key, the internal service secret, and the database URL) are validated at startup and
  fail fast in production if absent; the internal service URL must be HTTPS in
  production because it carries the internal secret and personal data.
- **WebSocket authentication** carries the JWT in the first WebSocket frame, never in the
  URL, so credentials are not exposed through request logs.

## 2. Access control and authorization

Access control satisfies the Application Development Guideline that sensitive locations
and functions must be gated so unauthorized users cannot reach them.

- **Role separation:** `require_instructor` / `require_student` dependencies gate every
  privileged route; a caller's role is derived from the verified JWT, never from a
  request body.
- **Ownership scoping:** instructor course operations resolve through a dependency that
  scopes by course owner and returns 404 (not 403) to avoid leaking course existence.
- **Enrolment scoping:** student surfaces require an active enrolment; course-instructor
  operations require an active instructor enrolment. Pending or rejected enrolments do
  not clear either gate. Course joining is only possible through the code-based join
  flow (with optional teacher approval) or Canvas roster sync.
- **Signed, single-use action tokens** are used where a link must carry authority
  (for example QR attendance), validated for signature and expiry and scoped to an
  active launch.
- **Database-layer defence in depth:** each request sets the current user id for
  row-level policies via a parameterized statement.
- **Internal service endpoints** authenticate with a constant-time shared-secret
  comparison, are excluded from the public API surface, and return uniform shapes so a
  caller cannot probe for the existence of a record.

## 3. Transport security and browser hardening

Satisfies the requirements for SSL/HTTPS on all logon and High-Risk pages, TLS for
network transport, and defence against common web attacks.

- **TLS everywhere** (Vercel, Railway, managed Postgres), with **HSTS**
  (`includeSubDomains; preload`) and `upgrade-insecure-requests`. Modern TLS is enforced
  by the managed platforms; no legacy SSL protocols are exposed.
- **Nonce-based Content-Security-Policy**, emitted per request: production `script-src`
  is `'self' 'nonce-…' 'strict-dynamic'` with no `unsafe-inline`; `object-src 'none'`,
  `base-uri 'self'`, and `frame-ancestors 'none'` are set.
- **Security headers:** `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: strict-origin-when-cross-origin`, and a restrictive
  `Permissions-Policy`.
- **Anti-CSRF posture:** the API is called with a Bearer token in a header rather than
  an ambient cookie, which removes the classic CSRF surface; Better Auth additionally
  sets `SameSite=Lax`, `HttpOnly` session cookies and validates the request origin
  against a trusted-origins list. Client-set cookies use `SameSite` and `Secure`.
- **Open-redirect defence:** callback and redirect URLs are normalized through the
  WHATWG URL parser and validated against the application's own origins.

## 4. Input validation and untrusted data

Satisfies the guideline that all user input be validated for type, syntax, length,
range, and permitted characters, and that critical flaws found in testing be corrected.

- **Pydantic v2** validates every request body at the API boundary.
- **Uploads** are validated by extension, MIME type, and magic-byte signature, with a
  size cap and parser timeouts. Stored object keys are derived from sanitized filenames
  plus fresh UUIDs, so a user cannot traverse paths or overwrite another user's object.
- **Server-Side Request Forgery defence:** URLs fetched from Canvas must be HTTPS on the
  default port and either allow-listed or not resolving to private, loopback,
  link-local, or reserved addresses; Canvas pagination links are pinned to the same host
  and scheme, blocking redirects to internal metadata endpoints.
- **LLM prompt handling:** student queries are sanitized and retrieved document content
  is placed in the user/context position of a prompt, not in system prompts or
  tool-calling schemas, so document content cannot redirect model authority.

## 5. Secrets and cryptography

Satisfies the requirement that sensitive data be encrypted and that credentials be
managed securely.

- Configuration is by environment variable with boot-time validation. No secrets are
  committed to source control (only example files are tracked).
- **Third-party tokens are encrypted at rest.** Canvas OAuth uses a single HKUST
  developer key with per-user access tokens stored encrypted with Fernet
  (AES-128-CBC + HMAC); the cipher fails closed if the key is unset. The OAuth `state`
  is a signed, short-lived token bound to an `HttpOnly`, `SameSite` cookie whose nonce
  is consumed atomically in the database, so an OAuth callback cannot be forged or
  replayed.

## 6. Logging, rate limiting, and error handling

Satisfies the SaaS logging requirement and the guideline to reduce attack surface and
avoid leaking sensitive data in errors.

- **Application logging** records authentication failures (with a key id and source IP,
  never the token) and attributes instructor and administrative actions to a user id.
- **Rate limiting** protects the cost-sensitive AI endpoints with a per-user hourly
  quota (instructor and student tiers); the quota is not consumed on error.
- **Error handling** returns a generic response envelope while full tracebacks are logged
  server-side only. Interactive API documentation is disabled in production. CORS is
  restricted to the single configured frontend origin with credentials (never a wildcard
  combined with credentials).

## 7. Cloud sub-processors (for the PIA and privacy notice)

Vercel (frontend), Railway (API and Postgres), Cloudflare R2 (object storage),
OpenRouter and OpenAI (embeddings and generation), and the vision-model captioning
provider process data outside Hong Kong. Audio for pronunciation is transient
(processed, not stored). These cross-border processors must be disclosed in the PDPO
privacy notice and covered by the Personal Data Privacy Impact Assessment.

## 8. Requirement mapping

### Minimum Security Standard, Application Systems

| ITSO requirement | How Meli meets it |
|---|---|
| Secure data transport (HTTPS) | TLS everywhere; HSTS preload; `upgrade-insecure-requests` |
| Application development (OWASP) | Pydantic validation, nonce CSP, security headers, SSRF guard, magic-byte upload checks, parameterized SQL |
| Access control on sensitive functions | Role gates, owner and enrolment scoping, 404-not-403, per-request DB user id |
| Ongoing third-party support | Actively maintained stack (Next.js, FastAPI, Postgres 17, pgvector) |
| Encryption of sensitive data | TLS in transit; Canvas tokens encrypted at rest (Fernet) |

### Minimum Security Standard, SaaS on Cloud

| ITSO requirement | How Meli meets it |
|---|---|
| Credential management / SSO | HKUST OIDC (Entra), tenant-pinned and signature-verified |
| Transport encryption (TLS) | Enforced by all managed providers |
| Logging for forensic use | Auth-failure and admin-action logging; per-user API usage table |
| Product selection / inventory | Vendor-neutral, portable architecture (plain SQL, S3-compatible storage, standard JWTs) |

### Application Development Guidelines

| Guideline | How Meli meets it |
|---|---|
| Design against OWASP Top 10 | Framework-level protections plus the controls in sections 1-6 |
| Access control on sensitive locations | Role, ownership, and enrolment gates (section 2) |
| Encrypt sensitive data in transit | TLS throughout (section 3) |
| Validate all user input | Pydantic v2 at every boundary; file type/size/timeout caps (section 4) |
| Anti-CSRF protection | Header Bearer tokens, SameSite cookies, origin validation (section 3) |
| Remove test data / accounts before production | Email/password disabled on the production host; seed data is development-only |
| Disable legacy SSL | Managed platforms enforce modern TLS only |

### Owned in the ITSO compliance register (operational, not application code)

CITARS registration, the Personal Data Privacy Impact Assessment, the Cloud Service
Provider checklist, the ITSO web-application vulnerability scan, multi-factor
authentication on provider admin accounts, and a tested backup/restore runbook are
tracked with CLE and ITSO rather than in this repository.
