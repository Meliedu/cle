"use client";

import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";

/**
 * Full-screen fallback shown when the backend-authoritative role query
 * (`GET /api/auth/me`) fails and settles. Offers a retry (re-fetch) and a
 * sign-out escape hatch. Rendered by both the legacy dashboard layout shell
 * and the `RoleGate` so the affordance lives in exactly one place.
 */
export function RoleLoadError() {
  const queryClient = useQueryClient();
  const { signOut } = useAuth();

  return (
    <div className="flex h-screen items-center justify-center bg-[var(--color-bg)]">
      <div className="mx-auto flex max-w-sm flex-col items-center gap-4 text-center">
        <h2 className="text-lg font-semibold text-[var(--color-text)]">
          We couldn&apos;t load your account
        </h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          Something went wrong while checking your account. You can retry, or
          sign out and sign back in.
        </p>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => {
              void queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
            }}
          >
            Retry
          </Button>
          <Button
            variant="link"
            onClick={() => {
              void signOut({ redirectUrl: "/sign-in" });
            }}
          >
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
