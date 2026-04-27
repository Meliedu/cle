// Compatibility shim that mirrors the Clerk `useAuth` and `useUser` shapes
// but is backed by Better Auth. Lets the ~25 components that called these
// hooks migrate via a single import-line change rather than per-call-site
// rewrites. Once the codebase has settled, individual call sites can be
// migrated to Better Auth's idiomatic `useSession` directly and this shim
// can be deleted.

"use client";

import { useCallback, useMemo } from "react";

import { authClient, useSession } from "@/lib/auth-client";

type GetTokenOptions = {
  // Clerk used named templates here; Better Auth has a single signing scheme,
  // so we accept and ignore the option for source-compat.
  template?: string;
};

type AuthShape = {
  getToken: (options?: GetTokenOptions) => Promise<string | null>;
  isSignedIn: boolean | undefined;
  isLoaded: boolean;
  userId: string | null | undefined;
  signOut: (options?: { redirectUrl?: string }) => Promise<void>;
};

export function useAuth(): AuthShape {
  const { data: session, isPending } = useSession();

  const getToken = useCallback(async () => {
    const { data } = await authClient.token();
    return data?.token ?? null;
  }, []);

  const signOut = useCallback(async ({ redirectUrl }: { redirectUrl?: string } = {}) => {
    await authClient.signOut();
    if (redirectUrl && typeof window !== "undefined") {
      window.location.assign(redirectUrl);
    }
  }, []);

  return {
    getToken,
    isSignedIn: isPending ? undefined : !!session,
    isLoaded: !isPending,
    userId: session?.user?.id ?? null,
    signOut,
  };
}

type UserShape = {
  user:
    | {
        id: string;
        primaryEmailAddress?: { emailAddress: string } | null;
        emailAddresses: Array<{ emailAddress: string }>;
        firstName: string | null;
        lastName: string | null;
        fullName: string | null;
        imageUrl: string;
      }
    | null
    | undefined;
  isLoaded: boolean;
  isSignedIn: boolean | undefined;
};

export function useUser(): UserShape {
  const { data: session, isPending } = useSession();
  const beUser = session?.user;

  // Stable identity: only rebuild the wrapper when one of the fields we
  // surface actually changes. Without this, every render of any consumer
  // (~30 files) gets a new `user` reference and downstream effects
  // keyed on `[user]` re-fire endlessly.
  return useMemo<UserShape>(() => {
    if (isPending) {
      return { user: undefined, isLoaded: false, isSignedIn: undefined };
    }
    if (!beUser) {
      return { user: null, isLoaded: true, isSignedIn: false };
    }
    const fullName = beUser.name ?? null;
    const [firstName = null, ...rest] = (fullName ?? "").trim().split(" ");
    const lastName = rest.length > 0 ? rest.join(" ") : null;
    return {
      user: {
        id: beUser.id,
        primaryEmailAddress: beUser.email
          ? { emailAddress: beUser.email }
          : null,
        emailAddresses: beUser.email ? [{ emailAddress: beUser.email }] : [],
        firstName,
        lastName,
        fullName,
        imageUrl: beUser.image ?? "",
      },
      isLoaded: true,
      isSignedIn: true,
    };
  }, [isPending, beUser?.id, beUser?.name, beUser?.email, beUser?.image]);
}
