"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  GraduationCap,
  ChevronLeft,
  X,
  LayoutDashboard,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRole } from "@/hooks/use-role";
import { SidebarSectionNav } from "@/components/layout/sidebar-section-nav";

interface SidebarProps {
  readonly mobileOpen?: boolean;
  readonly onMobileClose?: () => void;
}

/** Extract courseId from a pathname like /dashboard/courses/{uuid}/... */
function extractCourseId(pathname: string): string | null {
  const match = pathname.match(/\/courses\/([^/]+)/);
  return match ? match[1] : null;
}

/** Determine the active tab from search params or sub-page path. */
function resolveActiveTab(pathname: string, tabParam: string | null): string {
  // Sub-pages like /courses/{id}/revision, /courses/{id}/pronunciation, etc.
  const subPageMatch = pathname.match(/\/courses\/[^/]+\/(\w+)/);
  if (subPageMatch) {
    const segment = subPageMatch[1];
    // Map known sub-page routes to tab values
    const subPageMap: Record<string, string> = {
      revision: "revision",
      pronunciation: "pronunciation",
      live: "live",
      quizzes: "quizzes",
      flashcards: "flashcards",
    };
    if (segment in subPageMap) return subPageMap[segment];
  }
  return tabParam || "overview";
}

export function Sidebar({
  mobileOpen = false,
  onMobileClose,
}: SidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [collapsed, setCollapsed] = useState(false);

  const { role, isInstructor } = useRole();

  const courseId = extractCourseId(pathname);
  const activeTab = resolveActiveTab(pathname, searchParams.get("tab"));

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  const sidebarContent = (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div
        className={cn(
          "flex h-14 shrink-0 items-center border-b border-[var(--color-border)] px-4",
          collapsed ? "justify-center" : "gap-2"
        )}
      >
        <GraduationCap className="size-6 shrink-0 text-[var(--color-primary)]" />
        {!collapsed && (
          <span className="text-lg font-bold tracking-tight text-[var(--color-text)]">
            Meli
          </span>
        )}
      </div>

      {/* Scrollable nav area */}
      <div className="flex-1 overflow-y-auto py-3">
        {/* Dashboard link */}
        <div className="mb-2 px-2">
          <Link
            href="/dashboard"
            onClick={onMobileClose}
            className={cn(
              "flex items-center gap-2.5 rounded-[var(--radius-md)] px-2.5 py-2 text-sm font-medium transition-all duration-[var(--duration-fast)]",
              collapsed && "justify-center px-2",
              !courseId && pathname === "/dashboard"
                ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
            )}
          >
            <LayoutDashboard className="size-[18px] shrink-0 text-[var(--color-text-muted)]" />
            {!collapsed && <span>Dashboard</span>}
          </Link>
        </div>

        {/* Course section nav — only when viewing a course */}
        {courseId && (
          <SidebarSectionNav
            courseId={courseId}
            activeTab={activeTab}
            isInstructor={isInstructor}
            collapsed={collapsed}
            onMobileClose={onMobileClose}
          />
        )}
      </div>

      {/* Role indicator */}
      <div
        className={cn(
          "mx-2 mb-2 rounded-[var(--radius-md)] px-3 py-2",
          role === "instructor"
            ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
            : "bg-[var(--color-accent-light)] text-[var(--color-accent)]"
        )}
      >
        {!collapsed && (
          <p className="text-xs font-semibold uppercase tracking-wider">
            {role === "instructor" ? "Instructor" : "Student"}
          </p>
        )}
        {collapsed && (
          <p className="text-center text-xs font-bold">
            {role === "instructor" ? "I" : "S"}
          </p>
        )}
      </div>

      {/* Collapse toggle (desktop only) */}
      <div className="hidden border-t border-[var(--color-border)] p-2 md:block">
        <button
          onClick={toggleCollapse}
          className="flex w-full items-center justify-center rounded-[var(--radius-md)] py-2 text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-secondary)]"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <ChevronLeft
            className={cn(
              "size-4 transition-transform duration-[var(--duration-normal)]",
              collapsed && "rotate-180"
            )}
          />
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden md:flex h-screen flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)] transition-[width] duration-[var(--duration-normal)] ease-[var(--ease-out)]",
          collapsed ? "w-[60px]" : "w-[220px]"
        )}
      >
        {sidebarContent}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px] md:hidden"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <aside className="fixed inset-y-0 left-0 z-50 flex w-[260px] flex-col bg-[var(--color-surface)] shadow-[var(--shadow-lg)] md:hidden">
            <button
              onClick={onMobileClose}
              className="absolute right-3 top-4 rounded-[var(--radius-sm)] p-1 text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
              aria-label="Close sidebar"
            >
              <X className="size-5" />
            </button>
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  );
}
