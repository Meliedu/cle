"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { Role } from "@/hooks/use-role";
import {
  activeCourseKey,
  courseHref,
  courseNavForRole,
} from "@/components/layout/nav-config";

interface SidebarCourseNavProps {
  readonly role: Role;
  readonly courseId: string;
  readonly pathname: string;
  readonly onMobileClose?: () => void;
}

/**
 * The course-local rail: one flat list of stable destinations.
 *
 * This replaces the previous Before Class / In Class / After Class grouping.
 * The handoff removes those buckets outright (removal rule 04) because they
 * fragment tasks by time-of-day rather than by object, and they hid Sessions
 * entirely. Every entry here is a destination that exists for the whole life of
 * the course, so there is nothing left to group.
 *
 * Rendered only when a course is in scope; the caller owns that check.
 */
export function SidebarCourseNav({
  role,
  courseId,
  pathname,
  onMobileClose,
}: SidebarCourseNavProps) {
  const t = useTranslations("nav");
  const items = courseNavForRole(role);
  const activeKey = activeCourseKey(pathname, items);

  return (
    <nav aria-label={t("courseLabel")} className="flex flex-col gap-0.5 px-3">
      {items.map((item) => {
        const href = courseHref(role, courseId, item);
        const isActive = item.key === activeKey;
        const Icon = item.icon;

        return (
          <Link
            key={item.key}
            href={href}
            onClick={onMobileClose}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "relative flex h-11 items-center gap-3 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium outline-none transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-[var(--color-rail-text)] motion-reduce:transition-none",
              isActive
                ? "bg-[var(--color-rail-raised)] text-[var(--color-primary)]"
                : "text-[var(--color-rail-text-muted)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]"
            )}
          >
            {/* Honey spine marks the active course destination. The chip also
                changes background and text color, so this is never the only
                signal. */}
            {isActive ? (
              <span
                aria-hidden="true"
                className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-[var(--color-primary)]"
              />
            ) : null}
            <Icon
              className="size-[18px] shrink-0"
              strokeWidth={isActive ? 2.2 : 1.85}
              aria-hidden="true"
            />
            <span className="truncate">{t(`course.${item.key}`)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
