"use client";

import { useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { LogOut, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";
import { roleHomePath, useRole } from "@/hooks/use-role";
import { useCourses } from "@/hooks/use-courses";
import {
  activeCourseId,
  globalNavForRole,
} from "@/components/layout/nav-config";
import { SidebarCourseNav } from "@/components/layout/sidebar-section-nav";

interface SidebarProps {
  readonly mobileOpen?: boolean;
  readonly onMobileClose?: () => void;
}

/**
 * Fixed desktop rail width from the component contract:
 *
 *   GlobalShell | role, locale, activeGlobalRoute | Fixed 224 px desktop rail;
 *   responsive navigation is automatic, not a saved collapse preference
 *
 * There is deliberately no collapse control and no persisted width. Below the
 * `md` breakpoint the rail becomes an overlay drawer; that is the entire
 * responsive story (removal rule 03).
 */
const RAIL_WIDTH = 224;

export function Sidebar({ mobileOpen = false, onMobileClose }: SidebarProps) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const { signOut } = useAuth();
  const { role } = useRole();

  const courseId = activeCourseId(pathname);
  const { data: courses } = useCourses();
  const activeCourse = courseId
    ? courses?.find((course) => course.id === courseId) ?? null
    : null;

  const handleSignOut = useCallback(() => {
    void signOut({ redirectUrl: "/sign-in" });
  }, [signOut]);

  const globalItems = role ? globalNavForRole(role) : [];
  const brandHref = role ? roleHomePath(role) : "/dashboard";

  const isActive = (href: string): boolean =>
    pathname === href || pathname.startsWith(`${href}/`);

  const rail = (
    <div
      className="flex h-full flex-col bg-[var(--color-rail)] text-[var(--color-rail-text)]"
      style={{ width: RAIL_WIDTH }}
    >
      {/* Brand */}
      <div className="flex h-[68px] shrink-0 items-center gap-3 px-5">
        <Link
          href={brandHref}
          aria-label={t("brandHome")}
          onClick={onMobileClose}
          className="group flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary)] outline-none transition-transform duration-[var(--duration-normal)] hover:scale-105 focus-visible:ring-2 focus-visible:ring-[var(--color-rail-text)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-rail)] motion-reduce:transition-none motion-reduce:hover:scale-100"
        >
          <FloralMark className="size-[18px] text-[var(--color-text-on-primary)]" />
        </Link>
        <span className="text-[17px] font-semibold tracking-tight text-[var(--color-rail-text)]">
          Meli
        </span>
      </div>

      <div className="scrollbar-warm flex-1 overflow-y-auto pb-3">
        {/* Global destinations, present on every route */}
        <nav aria-label={t("mainLabel")} className="flex flex-col gap-0.5 px-3">
          {globalItems.map((item) => (
            <RailLink
              key={item.key}
              href={item.href}
              label={t(item.key)}
              icon={item.icon}
              active={isActive(item.href)}
              onClose={onMobileClose}
            />
          ))}
        </nav>

        {/*
          Course destinations, rendered only after course entry. Outside a
          course this whole block is absent, which is what keeps Sessions from
          existing as a global destination.
        */}
        {courseId && role ? (
          <>
            <div className="mx-5 my-5 border-t border-[var(--color-rail-border)]" />
            <div className="mb-3 px-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-rail-text-muted)]">
                {activeCourse?.code ?? t("courseLabel")}
              </p>
              {activeCourse?.name ? (
                <p
                  className="mt-1 line-clamp-2 text-[14px] font-medium leading-snug text-[var(--color-rail-text)]"
                  title={activeCourse.name}
                >
                  {activeCourse.name}
                </p>
              ) : null}
            </div>
            <SidebarCourseNav
              role={role}
              courseId={courseId}
              pathname={pathname}
              onMobileClose={onMobileClose}
            />
          </>
        ) : null}
      </div>

      {/* Bottom actions */}
      <div className="flex flex-col gap-0.5 border-t border-[var(--color-rail-border)] px-3 py-3">
        <button
          type="button"
          onClick={handleSignOut}
          className="flex h-11 w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium text-[var(--color-rail-text-muted)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-rail-text)] motion-reduce:transition-none"
        >
          <LogOut
            className="size-[18px] shrink-0"
            strokeWidth={1.85}
            aria-hidden="true"
          />
          <span>{t("logout")}</span>
        </button>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: fixed rail, always expanded */}
      <aside className="hidden h-full shrink-0 md:block">{rail}</aside>

      {/* Below md: overlay drawer. Automatic, not a stored preference. */}
      {mobileOpen ? (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <aside
            className="fixed inset-y-0 left-0 z-50 md:hidden"
            aria-label={t("navigationLabel")}
          >
            <button
              onClick={onMobileClose}
              className="absolute right-2 top-3 z-10 flex size-11 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-rail-text-muted)] outline-none hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-rail-text)]"
              aria-label={t("closeNavigation")}
            >
              <X className="size-5" />
            </button>
            {rail}
          </aside>
        </>
      ) : null}
    </>
  );
}

interface RailLinkProps {
  readonly href: string;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly active: boolean;
  readonly onClose?: () => void;
}

function RailLink({ href, label, icon: Icon, active, onClose }: RailLinkProps) {
  return (
    <Link
      href={href}
      onClick={onClose}
      aria-current={active ? "page" : undefined}
      className={cn(
        // h-11 = 44px, meeting the implementation touch-target floor.
        "flex h-11 items-center gap-3 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium outline-none transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-[var(--color-rail-text)] motion-reduce:transition-none",
        active
          ? "bg-[var(--color-rail-raised)] text-[var(--color-primary)]"
          : "text-[var(--color-rail-text-muted)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]"
      )}
    >
      <Icon
        className="size-[18px] shrink-0"
        strokeWidth={active ? 2.2 : 1.85}
        aria-hidden="true"
      />
      <span className="truncate">{label}</span>
    </Link>
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
