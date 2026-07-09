# Meli — HKUST OIDC Redirect URIs (verified against the code)

**Status:** Verified. Supersedes the *inferred* paths in
`docs/meli_docs/Meli_Session_Handoff.md` §3.2.
**App:** CLE-Meli (Next.js frontend, Better Auth self-hosted).
**Auth library:** `better-auth@1.6.23`, generic-OAuth (OIDC) plugin.
**Prepared for:** HKUST ITSO (redirect-URI registration in Microsoft Entra).

---

## 1. Verified callback path

Better Auth's generic-OAuth plugin mounts the OAuth callback at
`/oauth2/callback/:providerId`, **relative to the auth basePath**. Our
instance uses the default basePath `/api/auth` (no `basePath` override in
`src/lib/auth.ts`), so the full, browser-facing redirect URI is:

```
{origin}/api/auth/oauth2/callback/{providerId}
```

### Evidence

1. **Installed source** —
   `frontend/node_modules/better-auth/dist/plugins/generic-oauth/routes.mjs`:
   ```js
   const oAuth2Callback = (options) =>
     createAuthEndpoint("/oauth2/callback/:providerId", { ... })
   ```
   and `.../generic-oauth/index.mjs` builds the default redirect URI as:
   ```js
   redirectURI: `${ctx.baseURL}/oauth2/callback/${c.providerId}`
   ```
   (`ctx.baseURL` already includes the `/api/auth` basePath.)

2. **Official docs** (Context7, better-auth generic-oauth plugin):
   > The default callback URL will be
   > `${baseURL}/api/auth/oauth2/callback/:providerId`, and your OAuth
   > provider must be configured to use this specific URL.

3. **basePath** — `src/lib/auth.ts` calls `betterAuth({...})` with no
   `basePath`, so the default `/api/auth` applies (consistent with the JWKS
   endpoint the backend already consumes at `/api/auth/jwks`).

`providerId` is our choice, set in `src/lib/auth.ts`. We use **`hkust`**
(staff) and **`hkust-student`** — two distinct provider IDs so the two Entra
tenants never collide on a shared callback path. The staff ID is bare `hkust`
because that is the redirect URI HKUST registered on the staff Entra app
(see §4 — decision resolved).

---

## 2. Redirect URIs to register

Origins (from handoff §3.2 / §4):

| Env   | Origin |
|-------|--------|
| Local | `http://localhost:3000` |
| Dev   | `https://cle-meli-dev.hkust.edu.hk` |
| Prod  | `https://cle-meli.hkust.edu.hk` |

**Sign-in entry URL** (app login page, same for both tenants):
`https://cle-meli.hkust.edu.hk`

### 2.1 Staff provider — `providerId = hkust`

| Env   | Redirect URI |
|-------|--------------|
| Local | `http://localhost:3000/api/auth/oauth2/callback/hkust` |
| Dev   | `https://cle-meli-dev.hkust.edu.hk/api/auth/oauth2/callback/hkust` |
| Prod  | `https://cle-meli.hkust.edu.hk/api/auth/oauth2/callback/hkust` |

Per the ITSO/CLE email (2026-07), the staff app is registered with the Dev
and Prod URIs above, plus bare `http://localhost:3000` — **not** the full
local callback path. Local staff sign-in will fail with a redirect-URI
mismatch until `http://localhost:3000/api/auth/oauth2/callback/hkust` is
added to the staff app registration (flagged back to ITSO; does not affect
Dev/Prod).

### 2.2 Student provider — `providerId = hkust-student`

| Env   | Redirect URI |
|-------|--------------|
| Local | `http://localhost:3000/api/auth/oauth2/callback/hkust-student` |
| Dev   | `https://cle-meli-dev.hkust.edu.hk/api/auth/oauth2/callback/hkust-student` |
| Prod  | `https://cle-meli.hkust.edu.hk/api/auth/oauth2/callback/hkust-student` |

---

## 3. Tenant & application IDs

| Item | Value | Source |
|------|-------|--------|
| Staff tenant GUID | `c917f3e2-9322-4926-9bb3-daca730413ca` | handoff §3.1 |
| CLE-Meli **staff** app (client ID) | `830c7819-96e7-4fef-af23-407d4b4365ed` | handoff §3.1 |
| Staff discovery URL | `https://login.microsoftonline.com/c917f3e2-9322-4926-9bb3-daca730413ca/v2.0/.well-known/openid-configuration` | handoff §3.1 |
| Student tenant GUID | **pending ITSO** (different GUID) | handoff §3.1 |
| CLE-Meli **student** app (client ID) | **pending ITSO** | handoff §3.1 |
| Student discovery URL | **pending ITSO** (`.../{student-tenant}/v2.0/.well-known/openid-configuration`) | handoff §3.1 |

---

## 4. RESOLVED — staff callback path is `hkust` (not `hkust-staff`)

The CLE/ITSO email (2026-07) confirmed the staff Entra app is registered
with redirect URIs ending in `.../callback/hkust`:

```
https://cle-meli.hkust.edu.hk/api/auth/oauth2/callback/hkust
https://cle-meli-dev.hkust.edu.hk/api/auth/oauth2/callback/hkust
http://localhost:3000
```

We took the "rename our providerId" path: the staff provider in
`src/lib/auth.ts` (and the sign-in button) is now **`hkust`**, matching the
registration as-is with no ITSO round-trip. The student provider stays
`hkust-student` — asymmetric but harmless. Remaining loose end: the local
entry is the bare origin, not the full callback path (see §2.1 note).

---

## 5. Secrets & security notes

- **Secrets are never committed.** They live only in environment variables.
  Names (see `frontend/.env.example`):
  - `HKUST_STAFF_MELI_CLIENT_ID`, `HKUST_STAFF_MELI_CLIENT_SECRET`,
    `HKUST_STAFF_DISCOVERY_URL`
  - `HKUST_STUDENT_MELI_CLIENT_ID`, `HKUST_STUDENT_MELI_CLIENT_SECRET`,
    `HKUST_STUDENT_DISCOVERY_URL`
- **Staff client secret expires 2028-06-28** (ITSO email). Because it arrived
  over plaintext email, consider rotating it in Entra once sign-in works.
- Each provider is only activated when its `clientId` + `clientSecret` +
  `discoveryUrl` are all present (`src/lib/auth.ts` filters incomplete slots
  and only mounts the plugin when at least one survives). Until then the OIDC
  path is fully dormant — no runtime change.
- The UI buttons ("HKUST Staff" / "HKUST Student") render only when
  `NEXT_PUBLIC_HKUST_SSO=enabled`, so activation is a pure env-var drop.

---

## 6. Authorization / access-control notes (for ITSO review)

HKUST SSO authenticates any valid HKUST account; **the app authorises.** Two
gates, both keyed on `user.create` so they apply to OIDC sign-ups exactly as
they already do for Microsoft-social and email/password sign-ups:

1. **Email-domain gate (already live).** `detectRoleFromEmail()`
   (`src/lib/auth-domain.ts`) runs in the `databaseHooks.user.create.before`
   hook in `src/lib/auth.ts`. It rejects any address outside
   `ust.hk` / `connect.ust.hk` and assigns the role by domain. Throwing there
   aborts the row create in the same transaction, so a denied SSO user leaves
   **no** orphan in `auth.user`. The `.after` hook then POSTs to the FastAPI
   `/api/internal/users/link` endpoint to create/link the `public.users` row.
   *Confirmed:* these hooks fire on the generic-OAuth sign-up path because
   Better Auth funnels every new user through `user.create` regardless of
   sign-in method.

2. **Affiliation-claim gate (TO WIRE when providers activate).** Handoff §3
   calls for denying other-tenant accounts using
   `eduPersonAffiliation` / `voPersonAffiliation` claims (deny
   `@cityu.edu.hk`, `@polyu.edu.hk`, etc.) rather than trusting the email
   domain alone. This is **out of scope** for the dormant slots and should be
   added when the OIDC providers go live — likely via a `getUserInfo` /
   claim-mapping step on each generic-OAuth provider plus a check in the
   `user.create.before` hook. Tracked here so it is not forgotten.

3. **PKCE (TO WIRE when providers activate).** Set `pkce: true` on **both**
   generic-OAuth provider configs in `src/lib/auth.ts` at activation. Entra
   ID supports (and Microsoft recommends) PKCE on the authorization-code
   flow even for confidential clients — it hardens against
   authorization-code interception. One line per provider.

4. **Entra email-claim mapping (TO WIRE when providers activate).** Entra ID
   tokens do not always populate the `email` claim — the address often
   arrives only in `preferred_username` (or `upn`). If `user.email` comes
   through empty or non-address-shaped, the email-domain gate in (1) would
   misfire. At activation, add an explicit claim-mapping step on each
   provider (e.g. a `getUserInfo` override that sets
   `email = email ?? preferred_username`, lowercased) and verify with a real
   staff + student account that `detectRoleFromEmail()` sees the expected
   `@ust.hk` / `@connect.ust.hk` value.

---

## 7. Change log

- Verified callback pattern against `better-auth@1.6.23` installed source +
  official docs. Replaced the inferred `.../callback/hkust` /
  `.../callback/hkust-student` split (handoff §3.2) with the verified
  `.../api/auth/oauth2/callback/{providerId}` pattern and standardised the
  staff provider on `hkust-staff` (pending the §4 decision).
- 2026-07-09: §4 resolved by CLE/ITSO email — staff app is registered as
  `.../callback/hkust`, so the staff providerId was renamed `hkust-staff` →
  `hkust` in `src/lib/auth.ts`, `components/auth/hkust-sso-buttons.tsx`, and
  `.env.example`. Flagged the bare `http://localhost:3000` local entry back
  to ITSO (full callback path needed for local staff sign-in).
