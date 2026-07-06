// Client-side Better Auth helper. Imported by React components and hooks.
// The `jwtClient` plugin adds `authClient.token()` which returns a signed JWT
// suitable for the FastAPI backend's PyJWKClient verifier.

import { createAuthClient } from "better-auth/react";
import { jwtClient, genericOAuthClient } from "better-auth/client/plugins";

// Omitting baseURL lets Better Auth default to window.location.origin in
// the browser, which is the correct same-origin behavior. The previous
// "http://localhost:3000" fallback caused a mixed-content fetch from
// production HTTPS pages that browsers silently dropped — leaving the
// sign-in spinner stuck forever.
export const authClient = createAuthClient({
  // genericOAuthClient types the `authClient.signIn.oauth2({ providerId })`
  // action used by the HKUST Staff / Student SSO buttons on the sign-in page.
  // It is inert unless the matching server-side genericOAuth providers are
  // configured (see src/lib/auth.ts), so it adds no behavior on its own.
  plugins: [jwtClient(), genericOAuthClient()],
});

export const { useSession, signIn, signOut, signUp } = authClient;
