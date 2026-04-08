"use client";

import { useState, useCallback } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Navbar } from "@/components/layout/navbar";

interface DashboardShellProps {
  readonly children: React.ReactNode;
  readonly role?: "instructor" | "student";
}

export function DashboardShell({
  children,
  role = "student",
}: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleMenuClick = useCallback(() => {
    setMobileOpen(true);
  }, []);

  const handleMobileClose = useCallback(() => {
    setMobileOpen(false);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg)]">
      <Sidebar
        role={role}
        mobileOpen={mobileOpen}
        onMobileClose={handleMobileClose}
      />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Navbar onMenuClick={handleMenuClick} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
