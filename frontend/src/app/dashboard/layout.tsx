"use client";

import { Toaster } from "sonner";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { GenerationDock } from "@/components/generation/generation-dock";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { GenerationJobsProvider } from "@/hooks/use-generation-jobs";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isLoaded } = useRole();

  if (!isLoaded) {
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
