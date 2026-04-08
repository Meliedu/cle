"use client";

import { useUser } from "@clerk/nextjs";
import { DashboardShell } from "@/components/layout/dashboard-shell";
import { Skeleton } from "@/components/ui/skeleton";

function detectRole(email: string | undefined): "instructor" | "student" {
  if (!email) return "student";
  if (email.endsWith("@ust.hk")) return "instructor";
  return "student";
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoaded } = useUser();

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

  const role = detectRole(user?.primaryEmailAddress?.emailAddress);

  return <DashboardShell role={role}>{children}</DashboardShell>;
}
