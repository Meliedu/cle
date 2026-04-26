"use client";

import { useState, useCallback, Suspense } from "react";
import { Sidebar } from "@/components/layout/sidebar";
import { Navbar } from "@/components/layout/navbar";

interface DashboardShellProps {
  readonly children: React.ReactNode;
}

export function DashboardShell({ children }: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleMenuClick = useCallback(() => setMobileOpen(true), []);
  const handleMobileClose = useCallback(() => setMobileOpen(false), []);

  return (
    <div className="relative flex h-[100svh] overflow-hidden bg-[var(--color-surface)]">
      <Suspense fallback={null}>
        <Sidebar mobileOpen={mobileOpen} onMobileClose={handleMobileClose} />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col">
        <Suspense fallback={null}>
          <Navbar onMenuClick={handleMenuClick} />
        </Suspense>
        <main className="scrollbar-warm flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
