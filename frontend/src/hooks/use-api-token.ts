import { useCallback } from "react";

import { authClient } from "@/lib/auth-client";

/**
 * Returns a function that resolves to the bearer JWT for the FastAPI backend,
 * or null if no session is active. The token is signed by Better Auth's JWT
 * plugin and verified server-side via the JWKS endpoint at /api/auth/jwks.
 *
 * The hook signature is intentionally identical to the previous Clerk-backed
 * implementation so callers (~25 files) require no changes.
 */
export function useApiToken(): () => Promise<string | null> {
  return useCallback(async () => {
    const { data } = await authClient.token();
    return data?.token ?? null;
  }, []);
}
