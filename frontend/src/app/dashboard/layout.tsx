"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { Button } from "@/components/ui/button";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { GenerationDock } from "@/components/generation/generation-dock";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/use-auth";
import { useRole } from "@/hooks/use-role";
import { GenerationJobsProvider } from "@/hooks/use-generation-jobs";

function RoleLoadError() {
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

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isLoaded, isError } = useRole();

  if (!isLoaded) {
    if (isError) {
      return <RoleLoadError />;
    }
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--color-bg)]">
        <div className="space-y-3 text-center">
          <Skeleton className="mx-auto h-8 w-32" />
          <Skeleton className="mx-auto h-4 w-48" />
        </div>
      </div>
    );
  }

  return (
    <GenerationJobsProvider>
      <DashboardShell>{children}</DashboardShell>
      <GenerationDock />
      <Toaster position="bottom-right" richColors closeButton />
    </GenerationJobsProvider>
  );
}
