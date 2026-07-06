"use client";

import { AppShell } from "@/components/layout/app-shell";
import { RoleGate } from "@/components/layout/role-gate";

export default function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShell>
      <RoleGate allow="student">{children}</RoleGate>
    </AppShell>
  );
}
