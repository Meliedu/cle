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

import {
  detectRoleFromEmail,
  DisallowedEmailDomainError,
  ALLOWED_DOMAINS,
} from "@/lib/auth-domain";
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
// HKUST OIDC (Entra ID) — dormant until env vars are supplied.
//
// HKUST runs TWO separate Microsoft Entra tenants: a Staff tenant (@ust.hk)
// and a Student tenant (@connect.ust.hk). Each needs its own OIDC app
// registration (client id, secret, discovery URL), so we configure two
// generic-OAuth providers and route users at login (see the sign-in page's
// "HKUST Staff" / "HKUST Student" buttons).
//
// Both slots stay OFF until their env vars exist: any provider missing a
// clientId / clientSecret / discoveryUrl is filtered out, and the plugin is
// only registered when at least one provider survives the filter. With no
// env vars set (today's state) this contributes ZERO behavior change.
//
// VERIFIED callback path (better-auth 1.6.23 generic-oauth plugin):
//   ${baseURL}/api/auth/oauth2/callback/{providerId}
// i.e. /api/auth/oauth2/callback/hkust and .../hkust-student.
// Route registered as "/oauth2/callback/:providerId" under basePath
// "/api/auth" — see docs/oidc-redirect-uris.md for the evidence trail.
//
// The staff providerId is bare "hkust" (not "hkust-staff") because the staff
// Entra app was registered by HKUST with redirect URIs ending in
// .../callback/hkust (ITSO email 2026-07). The registered URI wins — renaming
// on our side is a one-line change; re-registering theirs is a round-trip.
//
// The email-domain gate + user-linking databaseHooks below fire on
// `user.create` regardless of sign-in method, so OIDC sign-ups are gated and
// linked to public.users exactly like Microsoft-social and email/password
// sign-ups. Affiliation-claim gating (eduPersonAffiliation) is a to-wire item
// tracked in the ITSO doc; it is intentionally out of scope here.
const hkustOidcProviders = [
  {
    providerId: "hkust",
    // Canonical names carry the MELI_ infix (the HKUST tenant hosts a second
    // app, XiYouQuest, so secrets are disambiguated per app). The deployed
    // Vercel project predates that convention and stores the staff pair as
    // HKUST_STAFF_CLIENT_ID / _SECRET — accept both so neither store breaks.
    clientId:
      process.env.HKUST_STAFF_MELI_CLIENT_ID ??
      process.env.HKUST_STAFF_CLIENT_ID ??
      "",
    clientSecret:
      process.env.HKUST_STAFF_MELI_CLIENT_SECRET ??
      process.env.HKUST_STAFF_CLIENT_SECRET ??
      "",
    discoveryUrl: process.env.HKUST_STAFF_DISCOVERY_URL ?? "",
    scopes: ["openid", "profile", "email"],
  },
  {
    providerId: "hkust-student",
    clientId: process.env.HKUST_STUDENT_MELI_CLIENT_ID ?? "",
    clientSecret: process.env.HKUST_STUDENT_MELI_CLIENT_SECRET ?? "",
    discoveryUrl: process.env.HKUST_STUDENT_DISCOVERY_URL ?? "",
    scopes: ["openid", "profile", "email"],
  },
].filter((p) => p.clientId && p.clientSecret && p.discoveryUrl);

export const auth = betterAuth({
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL,
  // Defense-in-depth against open redirects / CSRF: only our own origin may
  // receive auth callbacks and redirects. The client-side sanitizeRedirect
  // guard (src/lib/redirect.ts) is the first line; this is the server-side
  // backstop. Deliberately minimal — one origin, derived from baseURL.
  trustedOrigins: [baseURL],

  emailAndPassword: {
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
