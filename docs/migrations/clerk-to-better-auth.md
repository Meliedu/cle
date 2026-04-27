# Clerk → Better Auth migration playbook

Captures what shipped on `migrate/better-auth` (April 2026). Use this as
the canonical reference whenever an older spec under `docs/superpowers/`
mentions Clerk.

## Why we moved off Clerk

1. The "Secured by Clerk" branding required upgrading off the free tier
   (Pro at $25 / month at minimum).
2. Per-MAU pricing ($0.02 above 10K MAU) scales poorly for a HKUST-wide
   rollout where the active student population is well above the free
   ceiling.

## What replaced it

| Layer | Today |
|---|---|
| Identity provider | **Better Auth 1.6** (self-hosted, library) |
| Token format | EdDSA-signed JWT, verified server-side via JWKS |
| JWKS endpoint | `${BETTER_AUTH_URL}/api/auth/jwks` (Next.js route) |
| Tables | `auth.user`, `auth.session`, `auth.account`, `auth.verification`, `auth.jwks` — same Postgres as the rest of the app, separate `auth` schema |
| Local users row | `public.users` keyed on `users.better_auth_id` (1:1 with `auth.user.id`) |
| Email | **Resend** for verification + password reset (Clerk previously did this for free) |
| Social providers | Microsoft (Entra ID) — gated on `NEXT_PUBLIC_MICROSOFT_SSO_ENABLED` until the production app is registered inside the HKUST tenant |

## Architecture in one paragraph

The Next.js app runs Better Auth at `app/api/auth/[...all]/route.ts`. The
React client (`src/lib/auth-client.ts`) ships email/password and Microsoft
sign-in flows; on every backend call, `useApiToken` calls
`authClient.token()` to mint a fresh JWT. FastAPI verifies the JWT with
`PyJWKClient` against `BETTER_AUTH_JWKS_URL` and resolves the local user
by `users.better_auth_id`. Sign-up flows fire a
`databaseHooks.user.create.after` hook that POSTs to the FastAPI endpoint
`POST /api/internal/users/link` (guarded by `BETTER_AUTH_INTERNAL_SECRET`)
to create or link the `public.users` row. Account deletion calls Better
Auth's `deleteUser` flow whose `beforeDelete` hook POSTs to
`POST /api/internal/users/delete` — the backend refuses the deletion when
the user still owns courses or uploaded documents, so two-store state
never diverges.

## Migration steps that ran (for reference)

1. **Phase 0 — scaffolding.** Added `users.better_auth_id` (nullable +
   unique) via Alembic `b7e3d4f6a8c2`. Installed `better-auth`, `pg`,
   `bcrypt`, `resend` in the frontend. Wrote `lib/auth.ts`,
   `lib/auth-client.ts`, `lib/auth-domain.ts`, `lib/auth-email.ts`.

2. **Phase 1 — dual-run.** Created `auth` schema, ran
   `npx @better-auth/cli migrate` to materialize Better Auth's 5 tables.
   Mounted `app/api/auth/[...all]/route.ts`. Updated `verify_jwt` to
   accept either Clerk or Better Auth JWTs, routed by the `iss` claim.
   Added `app/api/internal.py` for the link endpoint.

3. **Phase 2 — frontend cutover.** Replaced `<ClerkProvider>` with
   nothing (Better Auth doesn't need a provider). Rewrote `proxy.ts` to
   use `auth.api.getSession`. Replaced `useApiToken` (callers untouched).
   Added a compat shim `hooks/use-auth.ts` mimicking Clerk's
   `useAuth`/`useUser` shape so the ~30 component imports could be
   updated via a single `sed` per file.

4. **Phase 2.5 — UI parity.** Ten primitives under `components/auth/`
   (`auth-shell`, `auth-card`, `text-field`, `auth-buttons`,
   `microsoft-button`, `divider-label`, `auth-link-row`, `field-error`,
   `password-strength-meter`, `honeycomb-mark`). Five pages refactored
   (`/sign-in`, `/sign-up`, `/verify-email`, `/forgot-password`,
   `/reset-password`). Sonner mounted in `app/layout.tsx`.

5. **Phase 3 — backend final cutover.** `get_current_user` and the
   rate-limit middleware now look up `User.better_auth_id` exclusively
   when the JWT is from Better Auth.

6. **Phase 4 — user migration.**
   `backend/scripts/migrate_clerk_to_better_auth.py`:
   - Reads `public.users` rows where `better_auth_id IS NULL`.
   - Creates `auth.user` rows with `emailVerified=true`.
   - Updates `users.better_auth_id` by email match.
   - Idempotent. `--dry-run` and `--live`.
   - **Passwords are NOT transferred.** Migrated users use
     "Forgot password?" on `/sign-in`.

7. **Phase 5 — decommission.** Alembic `c8f5e2a4b6d3` drops
   `users.clerk_id`, makes `better_auth_id` NOT NULL. `@clerk/nextjs`
   uninstalled. All `clerk_*` settings removed from `app/config.py`.
   `verify_clerk_token` alias removed.

## Account settings (`/dashboard/settings`)

Built in the same pass:
- **Profile**: edit name (`authClient.updateUser`); email + role read-only.
- **Security**: change password (`authClient.changePassword`) with
  optional "sign out other sessions"; minimum length 8.
- **Danger zone**: delete account requires typing
  `delete my account` to confirm; backend refuses with HTTP 409 if the
  user still owns courses or uploaded documents.

## Environment variables

### Backend (`.env`)
```
BETTER_AUTH_JWKS_URL=http://localhost:3000/api/auth/jwks
BETTER_AUTH_ISSUER=http://localhost:3000
BETTER_AUTH_AUDIENCE=meli-backend
BETTER_AUTH_INTERNAL_SECRET=<48 random bytes; openssl rand -base64 48>
```

### Frontend (`.env.local`)
```
BETTER_AUTH_SECRET=<openssl rand -base64 32>
BETTER_AUTH_URL=http://localhost:3000
BETTER_AUTH_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/langassistant
BETTER_AUTH_INTERNAL_SECRET=<same value as the backend one>
RESEND_API_KEY=re_...
RESEND_FROM_EMAIL=Meli <noreply@meli.app>
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=c917f3e2-9322-4926-9bb3-daca730413ca
NEXT_PUBLIC_MICROSOFT_SSO_ENABLED=false  # flip true once the prod Entra app is HKUST-internal
```

## Microsoft SSO — known issue

A Microsoft Entra app registered in a personal "Default Directory" tenant
will hit "Need admin approval" when an `@connect.ust.hk` user tries to
consent. To avoid that, the production app must be registered inside the
HKUST tenant by someone with permission. Until that's done, ship with
`NEXT_PUBLIC_MICROSOFT_SSO_ENABLED=false` and let users sign in with
email/password.

## Where to read the code

- `frontend/src/lib/auth.ts` — server config (provider, hooks, domain gate)
- `frontend/src/lib/auth-client.ts` — React client + JWT plugin
- `frontend/src/lib/auth-domain.ts` — `ALLOWED_DOMAINS` and role mapping
- `frontend/src/lib/auth-email.ts` — Resend wrappers
- `frontend/src/components/auth/*` — 10 UI primitives
- `frontend/src/app/{sign-in,sign-up,verify-email,forgot-password,reset-password,dashboard/settings}/page.tsx`
- `backend/app/services/auth.py` — `verify_jwt`, JWKS client, email-domain mapping
- `backend/app/api/deps.py` — `get_current_user` upsert
- `backend/app/api/internal.py` — link / delete endpoints
- `backend/scripts/migrate_clerk_to_better_auth.py` — the migration tool
