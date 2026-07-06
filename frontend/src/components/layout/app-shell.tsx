"use client";

import { Toaster } from "sonner";

import { DashboardShell } from "@/components/layout/dashboard-shell";
import { RoleLoadError } from "@/components/layout/role-load-error";
import { GenerationDock } from "@/components/generation/generation-dock";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { GenerationJobsProvider } from "@/hooks/use-generation-jobs";

interface AppShellProps {
  readonly children: React.ReactNode;
}

/**
 * Authenticated app frame shared by every role-scoped route tree (legacy
 * `/dashboard`, `/teacher/*`, `/student/*`). Blocks on the role query with a
 * skeleton, surfaces `RoleLoadError` if it fails, then mounts the sidebar +
 * navbar shell along with the generation dock and toaster. Role-lane guarding
 * is layered on top by `RoleGate` inside each role layout.
 */
export function AppShell({ children }: AppShellProps) {
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
