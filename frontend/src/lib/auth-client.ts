// Client-side Better Auth helper. Imported by React components and hooks.
// The `jwtClient` plugin adds `authClient.token()` which returns a signed JWT
// suitable for the FastAPI backend's PyJWKClient verifier.

import { createAuthClient } from "better-auth/react";
import { jwtClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL ?? "http://localhost:3000",
  plugins: [jwtClient()],
});

export const { useSession, signIn, signOut, signUp } = authClient;
