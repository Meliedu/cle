"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  GraduationCap,
  ChevronLeft,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  readonly label: string;
  readonly href: string;
  readonly icon: React.ComponentType<{ className?: string }>;
}

const instructorNav: readonly NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Courses", href: "/dashboard/courses", icon: BookOpen },
] as const;

const studentNav: readonly NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "My Courses", href: "/dashboard/courses", icon: BookOpen },
] as const;

interface SidebarProps {
  readonly role?: "instructor" | "student";
  readonly mobileOpen?: boolean;
  readonly onMobileClose?: () => void;
}

export function Sidebar({
  role = "student",
  mobileOpen = false,
  onMobileClose,
}: SidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const navItems = role === "instructor" ? instructorNav : studentNav;

  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => !prev);
  }, []);

  const isActive = (href: string): boolean => {
    if (href === "/dashboard") return pathname === "/dashboard";
    return pathname.startsWith(href);
  };

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

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-0.5">
          {navItems.map((item) => {
            const active = isActive(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={onMobileClose}
                  className={cn(
                    "group relative flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2 text-sm font-medium transition-all duration-[var(--duration-fast)]",
                    collapsed && "justify-center px-2",
                    active
                      ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                      : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
                  )}
                >
                  {/* Active indicator */}
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--color-primary)]" />
                  )}
                  <item.icon
                    className={cn(
                      "size-[18px] shrink-0 transition-colors duration-[var(--duration-fast)]",
                      active
                        ? "text-[var(--color-primary)]"
                        : "text-[var(--color-text-muted)] group-hover:text-[var(--color-text-secondary)]"
                    )}
                  />
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

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
            {/* Mobile close button */}
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
