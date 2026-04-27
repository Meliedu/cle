// Client-side Better Auth helper. Imported by React components and hooks.
// The `jwtClient` plugin adds `authClient.token()` which returns a signed JWT
// suitable for the FastAPI backend's PyJWKClient verifier.

import { createAuthClient } from "better-auth/react";
import { jwtClient } from "better-auth/client/plugins";

// Omitting baseURL lets Better Auth default to window.location.origin in
// the browser, which is the correct same-origin behavior. The previous
// "http://localhost:3000" fallback caused a mixed-content fetch from
// production HTTPS pages that browsers silently dropped — leaving the
// sign-in spinner stuck forever.
export const authClient = createAuthClient({
  plugins: [jwtClient()],
});

export const { useSession, signIn, signOut, signUp } = authClient;
