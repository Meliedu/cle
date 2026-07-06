"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import {
  ChevronsLeft,
  ChevronsRight,
  GraduationCap,
  LayoutDashboard,
  LogOut,
  Waypoints,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useRole } from "@/hooks/use-role";
import { useCourses } from "@/hooks/use-courses";
import { CANVAS_ENABLED } from "@/lib/features";
import { SidebarSectionNav } from "@/components/layout/sidebar-section-nav";

interface SidebarProps {
  readonly mobileOpen?: boolean;
  readonly onMobileClose?: () => void;
}

interface RailItem {
  readonly id: string;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly href?: string;
  readonly onClick?: () => void;
}

const RAIL_WIDTH_COLLAPSED = 72;
const RAIL_WIDTH_EXPANDED = 248;
const RAIL_STATE_KEY = "meli:rail-expanded";

function extractCourseId(pathname: string): string | null {
  const match = pathname.match(/\/courses\/([^/]+)/);
  return match ? match[1] : null;
}

function resolveActiveTab(pathname: string, tabParam: string | null): string {
  const subPageMatch = pathname.match(/\/courses\/[^/]+\/(\w+)/);
  if (subPageMatch) {
    const segment = subPageMatch[1];
    const subPageMap: Record<string, string> = {
      revision: "revision",
      pronunciation: "pronunciation",
      live: "live",
      quizzes: "quizzes",
      flashcards: "flashcards",
    };
    if (segment in subPageMap) return subPageMap[segment];
  }
  return tabParam ?? "overview";
}

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { signOut } = useAuth();
  const { isInstructor } = useRole();

  const courseId = extractCourseId(pathname);
  const activeTab = resolveActiveTab(pathname, searchParams.get("tab"));

  const { data: courses } = useCourses();
  const activeCourse = courseId
    ? courses?.find((c) => c.id === courseId) ?? null
    : null;

  // Persist rail expand/collapse between navigations. Initializer runs on the
  // client (this is a "use client" component that only mounts after the auth
  // gate, so there's no SSR hydration mismatch for the sidebar itself).
  const [expanded, setExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(RAIL_STATE_KEY) === "true";
  });
  const toggleExpanded = useCallback(() => {
    setExpanded((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        window.localStorage.setItem(RAIL_STATE_KEY, String(next));
      }
      return next;
    });
  }, []);

  const handleSignOut = useCallback(() => {
    void signOut({ redirectUrl: "/sign-in" });
  }, [signOut]);

  // These hrefs intentionally point at legacy /dashboard/* until P0 Task 7 wires config-driven per-lane nav.
  const primaryItems: readonly RailItem[] = [
    {
      id: "home",
      label: "Dashboard",
      icon: LayoutDashboard,
      href: "/dashboard",
    },
    {
      id: "courses",
      label: "Courses",
      icon: GraduationCap,
      href: "/dashboard/courses",
    },
    ...(isInstructor && CANVAS_ENABLED
      ? [
          {
            id: "canvas",
            label: "Canvas sync",
            icon: Waypoints,
            href: "/dashboard/canvas",
          } satisfies RailItem,
        ]
      : []),
  ];

  const bottomItems: readonly RailItem[] = [
    {
      id: "logout",
      label: "Log out",
      icon: LogOut,
      onClick: handleSignOut,
    },
  ];

  const isActive = (item: RailItem): boolean => {
    if (!item.href) return false;
    if (item.href === "/dashboard") {
      return pathname === "/dashboard";
    }
    return pathname === item.href || pathname.startsWith(`${item.href}/`);
  };

  const buildRail = (forceExpanded = false) => {
    const isExpanded = forceExpanded || expanded;
    const width = isExpanded ? RAIL_WIDTH_EXPANDED : RAIL_WIDTH_COLLAPSED;
    return (
      <div
        className="flex h-full flex-col bg-[var(--color-rail)] text-[var(--color-rail-text)] transition-[width] duration-[var(--duration-normal)] ease-[var(--ease-out)]"
        style={{ width }}
      >
        {/* Brand */}
        <div
          className={cn(
            "flex h-16 shrink-0 items-center",
            isExpanded ? "gap-3 pl-4 pr-3" : "justify-center"
          )}
        >
          <Link
            href="/dashboard"
            aria-label="Meli home"
            onClick={onMobileClose}
            className="group flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary)]/90 transition-transform duration-[var(--duration-normal)] hover:scale-105"
          >
            <FloralMark className="size-5 text-[var(--color-text-on-primary)]" />
          </Link>
          {isExpanded ? (
            <span className="text-lg font-semibold tracking-tight text-[var(--color-rail-text)]">
              Meli
            </span>
          ) : null}
        </div>

        {/* Scrollable middle — primary items + (when in a course) section nav */}
        <div className="scrollbar-warm flex-1 overflow-y-auto pb-3">
          {/* Primary */}
          <nav
            aria-label="Primary"
            className={cn(
              "flex flex-col gap-0.5",
              isExpanded ? "pl-3 pr-1.5" : "items-center px-1.5"
            )}
          >
            {primaryItems.map((item) => (
              <RailButton
                key={item.id}
                item={item}
                active={isActive(item)}
                expanded={isExpanded}
                onClose={onMobileClose}
              />
            ))}
          </nav>

          {/* Course section nav — only when we're inside a course */}
          {courseId ? (
            <>
              <div
                className={cn(
                  "my-4",
                  isExpanded ? "mx-4" : "mx-3",
                  "border-t border-[var(--color-rail-border)]"
                )}
              />
              {isExpanded && activeCourse ? (
                <div className="mb-3 pl-4 pr-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-rail-text-muted)]">
                    Course
                  </p>
                  <p
                    className="mt-1 line-clamp-2 text-[15px] font-semibold leading-snug text-[var(--color-rail-text)]"
                    title={activeCourse.name}
                  >
                    {activeCourse.name}
                  </p>
                </div>
              ) : null}
              <SidebarSectionNav
                courseId={courseId}
                activeTab={activeTab}
                isInstructor={isInstructor}
                collapsed={!isExpanded}
                variant="dark"
                onMobileClose={onMobileClose}
              />
            </>
          ) : null}
        </div>

        {/* Bottom actions */}
        <div
          className={cn(
            "flex flex-col gap-0.5 border-t border-[var(--color-rail-border)] py-3",
            isExpanded ? "pl-3 pr-1.5" : "items-center px-1.5"
          )}
        >
          {bottomItems.map((item) => (
            <RailButton
              key={item.id}
              item={item}
              active={false}
              expanded={isExpanded}
              onClose={onMobileClose}
            />
          ))}

          <button
            type="button"
            onClick={toggleExpanded}
            aria-label={isExpanded ? "Collapse sidebar" : "Expand sidebar"}
            aria-pressed={isExpanded}
            className={cn(
              "mt-1 flex items-center rounded-[var(--radius-lg)] text-[var(--color-rail-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]",
              isExpanded
                ? "h-10 w-full justify-start gap-3 pl-3 pr-2 text-[14px]"
                : "size-10 justify-center"
            )}
          >
            {isExpanded ? (
              <ChevronsLeft className="size-[18px]" strokeWidth={1.75} />
            ) : (
              <ChevronsRight className="size-[18px]" strokeWidth={1.75} />
            )}
            {isExpanded ? (
              <span className="text-[13px] font-medium">Collapse</span>
            ) : null}
          </button>

          <span
            className={cn(
              "mt-3 size-1.5 shrink-0 rounded-full bg-[var(--color-primary)]",
              isExpanded && "mx-3"
            )}
            aria-hidden="true"
            title={isInstructor ? "Instructor" : "Student"}
          />
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Desktop */}
      <aside className="hidden h-full shrink-0 md:block">{buildRail()}</aside>

      {/* Mobile overlay */}
      {mobileOpen ? (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm md:hidden"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <aside className="fixed inset-y-0 left-0 z-50 md:hidden">
            <button
              onClick={onMobileClose}
              className="absolute right-2 top-3 z-10 rounded-[var(--radius-sm)] p-1 text-[var(--color-rail-text-muted)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]"
              aria-label="Close sidebar"
            >
              <X className="size-5" />
            </button>
            {buildRail(true)}
          </aside>
        </>
      ) : null}
    </>
  );
}

interface RailButtonProps {
  readonly item: RailItem;
  readonly active: boolean;
  readonly expanded: boolean;
  readonly onClose?: () => void;
}

function RailButton({ item, active, expanded, onClose }: RailButtonProps) {
  const { icon: Icon, label, href, onClick } = item;

  const classes = cn(
    "flex items-center rounded-[var(--radius-lg)] font-medium transition-all duration-[var(--duration-fast)]",
    expanded ? "h-11 w-full gap-3 pl-3 pr-2 text-[15px]" : "size-11 justify-center",
    active
      ? "bg-[var(--color-rail-raised)] text-[var(--color-primary)]"
      : "text-[var(--color-rail-text-muted)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]"
  );

  const body = (
    <>
      <Icon
        className="size-[18px] shrink-0"
        strokeWidth={active ? 2.25 : 1.85}
      />
      {expanded ? <span className="truncate">{label}</span> : null}
      {!expanded ? <span className="sr-only">{label}</span> : null}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        onClick={onClose}
        className={classes}
        aria-label={label}
        title={!expanded ? label : undefined}
      >
        {body}
      </Link>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={classes}
      aria-label={label}
      title={!expanded ? label : undefined}
    >
      {body}
    </button>
  );
}

/** Small six-petal flower used as the brand mark on the dark rail. */
function FloralMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="currentColor"
      aria-hidden="true"
    >
      <circle cx="12" cy="6" r="3" />
      <circle cx="12" cy="18" r="3" />
      <circle cx="6" cy="9" r="3" />
      <circle cx="18" cy="9" r="3" />
      <circle cx="6" cy="15" r="3" />
      <circle cx="18" cy="15" r="3" />
      <circle cx="12" cy="12" r="2" fill="var(--color-rail)" />
    </svg>
  );
}
