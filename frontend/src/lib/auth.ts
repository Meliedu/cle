// Server-side Better Auth instance. Mounted by the catch-all route at
// `app/api/auth/[...all]/route.ts` (see Phase 1).
//
// Architecture notes:
// - Better Auth tables (user, session, account, verification, jwks) live in
//   the `auth` schema of the langassistant Postgres so they don't collide
//   with our public.users table. The schema is created by running
//   `psql -c "CREATE SCHEMA IF NOT EXISTS auth"` once before Better Auth's
//   own schema migration (`npx @better-auth/cli generate` / `migrate`).
// - Password hashing uses bcrypt to remain compatible with Clerk-exported
//   password hashes (Clerk uses bcrypt; Better Auth defaults to scrypt).
// - On every successful sign-up, we POST to the FastAPI backend's
//   `/api/internal/users/link` endpoint so the local public.users row is
//   created (or linked) with the appropriate role derived from the email
//   domain. This mirrors the auto-create behavior in the legacy
//   `get_current_user` Clerk path.

import { betterAuth } from "better-auth";
import { jwt, genericOAuth } from "better-auth/plugins";
import { createAuthMiddleware, APIError } from "better-auth/api";
import { dash } from "@better-auth/infra";
import { Pool } from "pg";
import bcrypt from "bcrypt";
import { decodeJwt } from "jose";

import {
  detectRoleFromEmail,
  DisallowedEmailDomainError,
  ALLOWED_DOMAINS,
} from "@/lib/auth-domain";
import { isEmailPasswordHost } from "@/lib/auth-flags";
import {
  sendResetPasswordEmail,
  sendVerificationEmail,
} from "@/lib/auth-email";

const databaseUrl =
  process.env.BETTER_AUTH_DATABASE_URL ??
  process.env.DATABASE_URL ??
  "postgresql://postgres:postgres@localhost:5432/langassistant";

const pool = new Pool({
  connectionString: databaseUrl,
  // Keep Better Auth tables in their own schema; fall through to `public` for
  // shared extensions (e.g. gen_random_uuid).
  options: "-c search_path=auth,public",
});

const internalApiUrl =
  process.env.INTERNAL_API_URL ?? "http://localhost:8000/api";
const internalSecret = process.env.BETTER_AUTH_INTERNAL_SECRET ?? "";

// Single source of truth for the app's own origin — used both as Better
// Auth's baseURL and as the sole trustedOrigin (defense-in-depth: Better
// Auth validates callback / redirect origins against this list, so a
// crafted cross-origin callbackURL is rejected server-side too).
const baseURL = process.env.BETTER_AUTH_URL ?? "http://localhost:3000";

// Fail fast at module load if BETTER_AUTH_SECRET is missing in production.
// Without it, Better Auth would silently generate a per-process random
// secret — invalidating sessions on restart and breaking multi-instance
// deployments.
if (
  process.env.NODE_ENV === "production" &&
  !process.env.BETTER_AUTH_SECRET
) {
  throw new Error(
    "BETTER_AUTH_SECRET is required in production. Generate with `openssl rand -base64 32`.",
  );
}

// `dash()` mounts /api/auth/dash/* and authenticates with BETTER_AUTH_API_KEY.
// Without a key, those endpoints could expose internal telemetry to anyone
// who discovers the path. Require a key in production; warn loudly in dev.
if (
  process.env.NODE_ENV === "production" &&
  !process.env.BETTER_AUTH_API_KEY
) {
  throw new Error(
    "BETTER_AUTH_API_KEY is required in production (used by the @better-auth/infra dash() plugin to authenticate /api/auth/dash/* endpoints).",
  );
}

async function linkUserOnBackend(input: {
  betterAuthId: string;
  email: string;
  fullName: string | null;
  imageUrl: string | null;
}): Promise<void> {
  if (!internalSecret) {
    if (process.env.NODE_ENV === "production") {
      throw new Error("BETTER_AUTH_INTERNAL_SECRET is not configured");
    }
    console.warn(
      "[auth] BETTER_AUTH_INTERNAL_SECRET unset; skipping users-link call",
    );
    return;
  }

  const response = await fetch(`${internalApiUrl}/internal/users/link`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Auth": internalSecret,
    },
    body: JSON.stringify({
      better_auth_id: input.betterAuthId,
      email: input.email,
      full_name: input.fullName,
      avatar_url: input.imageUrl,
    }),
  });

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(
      `Backend users-link failed: ${response.status} ${detail.slice(0, 200)}`,
    );
  }
}

// ---------------------------------------------------------------------------
// HKUST OIDC (Entra ID) — single multi-tenant provider.
//
// Per ITSO (Mandy email, 2026-07), both CLE apps authenticate through the
// MULTI-TENANT `/organizations/` endpoint: ONE app serves staff (@ust.hk) and
// students (@connect.ust.hk), and Microsoft routes each user to their home
// tenant by email domain. There is no need to split staff/student into
// separate providers or buttons.
//
// We supply EXPLICIT endpoints instead of a discovery URL on purpose: the
// `/organizations/` discovery `issuer` is the templated `.../{tenantid}/v2.0`,
// and Better Auth's RFC 9207 check compares the callback `iss` (the user's REAL
// tenant) against that template — rejecting every login with `issuer_mismatch`.
// With no discoveryUrl/issuer set, that check is skipped; the id_token
// (back-channel over TLS, PKCE) is the trusted profile source.
//
// providerId stays bare "hkust" to match the redirect URI HKUST registered
// (.../api/auth/oauth2/callback/hkust). The provider mounts once clientId +
// endpoints exist; the client secret is optional (public-client PKCE — Better
// Auth only sends client_secret when non-empty). The databaseHooks below still
// gate + link every OIDC sign-up by email domain.
const HKUST_AUTHORIZE_URL =
  "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize";
const HKUST_TOKEN_URL =
  "https://login.microsoftonline.com/organizations/oauth2/v2.0/token";

const hkustOidcProviders = [
  {
    providerId: "hkust",
    // The deployed Vercel project stores the staff pair as
    // HKUST_STAFF_CLIENT_ID / _SECRET; the canonical names carry a MELI_ infix.
    // Accept both so neither store breaks. Secret is optional (public client).
    clientId:
      process.env.HKUST_STAFF_MELI_CLIENT_ID ??
      process.env.HKUST_STAFF_CLIENT_ID ??
      "",
    clientSecret:
      process.env.HKUST_STAFF_MELI_CLIENT_SECRET ??
      process.env.HKUST_STAFF_CLIENT_SECRET ??
      "",
    authorizationUrl: HKUST_AUTHORIZE_URL,
    tokenUrl: HKUST_TOKEN_URL,
    scopes: ["openid", "profile", "email"],
    pkce: true,
    authorizationUrlParams: { prompt: "select_account" },
    // Entra frequently omits the `email` claim, so the default getUserInfo
    // (which needs id_token.email) would fall through to a userinfo URL we
    // don't configure. Decode the id_token ourselves, falling back to
    // preferred_username, so the email-domain gate always sees an address.
    getUserInfo: async (tokens: { idToken?: string }) => {
      if (!tokens.idToken) return null;
      const c = decodeJwt(tokens.idToken);
      if (!c.sub) return null;
      const email = String(
        (c.email as string) ?? (c.preferred_username as string) ?? "",
      ).toLowerCase();
      return {
        id: String(c.sub),
        email,
        emailVerified: true,
        name: String(
          (c.name as string) ?? (c.preferred_username as string) ?? "User",
        ),
        image:
          typeof c.picture === "string" ? (c.picture as string) : undefined,
      };
    },
  },
].filter((p) => p.clientId && p.authorizationUrl && p.tokenUrl);

// Credential-path endpoints rejected on SSO-only hosts (see the before-hook).
// Entries are better-auth's REGISTERED route templates for v1.6.23 — e.g. the
// password-reset request endpoint is /request-password-reset, NOT
// /forget-password (that path only exists in the email-otp plugin, which we
// don't use). auth-gate.test.ts asserts every entry exists in the endpoint
// registry so a renamed or misremembered path fails CI instead of silently
// un-gating production.
export const EMAIL_AUTH_PATHS: ReadonlySet<string> = new Set([
  "/sign-in/email",
  "/sign-up/email",
  "/request-password-reset",
  "/reset-password",
  "/reset-password/:token",
]);

export const auth = betterAuth({
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL,
  // Defense-in-depth against open redirects / CSRF: only our own origins may
  // receive auth callbacks and redirects. The client-side sanitizeRedirect
  // guard (src/lib/redirect.ts) is the first line; this is the server-side
  // backstop. The dev domain is included because prod and dev are ONE
  // deployment (baseURL points at prod): without it, better-auth rejects
  // every auth POST from cle-meli-dev with INVALID_ORIGIN — including the
  // email/password path that domain exists to keep.
  trustedOrigins: [baseURL, "https://cle-meli-dev.hkust.edu.hk"],

  emailAndPassword: {
    // Registered on every host, but the before-hook below rejects the email
    // sign-in/up/reset endpoints on the SSO-only production host. (Prod and dev
    // share one deployment, so a static per-env `enabled` can't tell them
    // apart — the gate has to be per-request by Host.)
    enabled: true,
    requireEmailVerification: true,
    minPasswordLength: 8,
    // bcrypt silently truncates after 72 bytes — cap inputs at 72 so a
    // user who sets a longer password isn't surprised when a shorter
    // prefix later authenticates with the same hash.
    maxPasswordLength: 72,
    autoSignIn: true,
    sendResetPassword: async ({ user, url }) => {
      await sendResetPasswordEmail(user.email, url);
    },
    // bcrypt for parity with Clerk-exported hashes (see Phase 4 migration).
    password: {
      hash: async (password) => bcrypt.hash(password, 12),
      verify: async ({ hash, password }) => bcrypt.compare(password, hash),
    },
  },

  emailVerification: {
    sendOnSignUp: true,
    autoSignInAfterVerification: true,
    sendVerificationEmail: async ({ user, url }) => {
      await sendVerificationEmail(user.email, url);
    },
  },

  user: {
    // Enables authClient.deleteUser(). The beforeDelete hook tells the
    // FastAPI backend to drop the linked public.users row and any cascaded
    // dependents. If the backend refuses (e.g. instructor still owns
    // courses), the hook re-throws and Better Auth aborts the deletion so
    // the two stores never diverge.
    deleteUser: {
      enabled: true,
      beforeDelete: async (user) => {
        if (!internalSecret) {
          if (process.env.NODE_ENV === "production") {
            throw new Error("BETTER_AUTH_INTERNAL_SECRET is not configured");
          }
          console.warn(
            "[auth] BETTER_AUTH_INTERNAL_SECRET unset; skipping backend delete",
          );
          return;
        }
        const response = await fetch(`${internalApiUrl}/internal/users/delete`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Internal-Auth": internalSecret,
          },
          body: JSON.stringify({ better_auth_id: user.id }),
        });
        if (!response.ok) {
          const detail = await response.text().catch(() => "");
          throw new Error(
            `Backend account-delete failed: ${response.status} ${detail.slice(0, 200)}`,
          );
        }
      },
    },
  },

  // HKUST uses Microsoft 365 — both ust.hk (faculty) and connect.ust.hk
  // (students) live in the HKUST Entra ID tenant, so Microsoft SSO is the
  // primary path. Email/password is kept on for testing only. We do not
  // enable Google or any other provider per product policy.
  //
  // Only register the provider when both credentials exist (mirrors the
  // genericOAuth filter above); otherwise Better Auth logs a "missing
  // clientId/clientSecret" warning on every request in dev. tenantId defaults
  // to "organizations" (work/school accounts only); set MICROSOFT_TENANT_ID to
  // the HKUST tenant GUID to lock to that tenant.
  socialProviders:
    process.env.MICROSOFT_CLIENT_ID && process.env.MICROSOFT_CLIENT_SECRET
      ? {
          microsoft: {
            clientId: process.env.MICROSOFT_CLIENT_ID,
            clientSecret: process.env.MICROSOFT_CLIENT_SECRET,
            tenantId: process.env.MICROSOFT_TENANT_ID ?? "organizations",
            prompt: "select_account",
          },
        }
      : {},

  plugins: [
    // Issues signed JWTs and exposes a JWKS endpoint at /api/auth/jwks
    // that the FastAPI backend consumes via PyJWKClient.
    jwt(),
    // Better Auth Infra dashboard — observability/telemetry plugin.
    // Reads BETTER_AUTH_API_KEY from env and exposes /api/auth/dash/*
    // for the hosted dashboard at https://dashboard.better-auth.com.
    dash(),
    // HKUST OIDC (staff + student Entra tenants). Only mounted when at least
    // one provider has full credentials — dormant with no env vars set.
    ...(hkustOidcProviders.length
      ? [genericOAuth({ config: hkustOidcProviders })]
      : []),
  ],

  hooks: {
    // Early rejection for /sign-up/email so the user gets a clean 400 before
    // the row is created. Microsoft / SSO signups can't be caught here
    // because the email isn't in the body yet — those go through the
    // databaseHooks.user.create.before path below, which runs after the
    // OAuth round-trip but BEFORE the row is committed.
    before: createAuthMiddleware(async (ctx) => {
      // SSO-only production gate. The email/password endpoints stay live on the
      // dev domain + localhost but are rejected on the production host — hiding
      // the form is not enough, since a direct API call would otherwise still
      // create/authenticate a credential account. Host is read per-request
      // because prod and dev are the same deployment.
      if (EMAIL_AUTH_PATHS.has(ctx.path)) {
        // Fail-closed on host. Email is allowed only when EVERY host signal
        // present (Host + X-Forwarded-Host) is an email host. This does NOT
        // rely on Vercel overwriting a client-supplied X-Forwarded-Host:
        // Vercel sets at least one of these authoritatively to the served
        // domain, so a request that actually arrived on the production host
        // always carries prod in Host and/or X-Forwarded-Host — spoofing just
        // one to a dev value still leaves the real prod host in the other, and
        // `.every()` blocks it. (Absent all host headers → also blocked.)
        const hostSignals = [
          ctx.headers?.get("host"),
          ctx.headers?.get("x-forwarded-host"),
        ].filter((h): h is string => Boolean(h));
        const emailAllowedHere =
          hostSignals.length > 0 && hostSignals.every(isEmailPasswordHost);
        if (!emailAllowedHere) {
          throw new APIError("FORBIDDEN", {
            message: "Email sign-in is disabled here. Please sign in with HKUST.",
          });
        }
      }

      if (ctx.path !== "/sign-up/email") return;
      const email = ctx.body?.email as string | undefined;
      if (!email) return;
      try {
        detectRoleFromEmail(email);
      } catch (error) {
        if (error instanceof DisallowedEmailDomainError) {
          throw new APIError("BAD_REQUEST", {
            message: `Only ${ALLOWED_DOMAINS.join(" / ")} email addresses are accepted.`,
          });
        }
        throw error;
      }
    }),
  },

  databaseHooks: {
    user: {
      create: {
        // Final domain gate — runs in the same transaction as the row
        // create, so throwing here aborts the create and leaves NO orphan
        // in auth.user. This is the only place that catches SSO sign-ups
        // (Microsoft etc.) where the email is only known after OAuth.
        before: async (user) => {
          try {
            detectRoleFromEmail(user.email);
          } catch (error) {
            if (error instanceof DisallowedEmailDomainError) {
              throw new APIError("BAD_REQUEST", {
                message: `Only ${ALLOWED_DOMAINS.join(" / ")} email addresses are accepted.`,
              });
            }
            throw error;
          }
        },
        after: async (user) => {
          // Link to (or create) a row in our public.users table so all
          // existing FK relationships keep resolving. Fires once per user.
          // If the backend is unreachable we delete the just-created
          // auth.user row to avoid leaving an orphan that can't sign in.
          try {
            await linkUserOnBackend({
              betterAuthId: user.id,
              email: user.email,
              fullName: user.name ?? null,
              imageUrl: user.image ?? null,
            });
          } catch (error) {
            try {
              await pool.query("DELETE FROM auth.user WHERE id = $1", [user.id]);
            } catch (cleanupError) {
              console.error(
                "[auth] failed to clean up orphan auth.user after backend link failure",
                cleanupError,
              );
            }
            throw error;
          }
        },
      },
    },
  },
});
