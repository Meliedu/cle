"use client";

import { AppShell } from "@/components/layout/app-shell";
import { RoleGate } from "@/components/layout/role-gate";

export default function TeacherLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AppShell>
      <RoleGate allow="instructor">{children}</RoleGate>
    </AppShell>
  );
}
