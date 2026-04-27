"use client";

import { usePathname, useSearchParams } from "next/navigation";
import Link from "next/link";
import { UserButton } from "@/components/layout/user-button";
import { Menu, ChevronRight } from "lucide-react";
import { LanguageToggle } from "@/components/layout/language-toggle";
import { useCourses } from "@/hooks/use-courses";

interface NavbarProps {
  readonly onMenuClick?: () => void;
}

const TAB_LABELS: Record<string, string> = {
  overview: "Overview",
  materials: "Materials",
  quizzes: "Quizzes",
  flashcards: "Flashcards",
  revision: "Revision",
  pronunciation: "Pronunciation",
  live: "Live Quiz",
  progress: "Progress",
  leaderboard: "Leaderboard",
  students: "Students",
};

const SUB_PAGE_LABELS: Record<string, string> = {
  revision: "Revision",
  pronunciation: "Pronunciation",
  live: "Live Quiz",
  quizzes: "Quiz",
  flashcards: "Flashcards",
};

interface Crumb {
  label: string;
  href: string;
}

function useBreadcrumbs(): readonly Crumb[] {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: courses } = useCourses();

  const crumbs: Crumb[] = [{ label: "Dashboard", href: "/dashboard" }];

  // Match /dashboard/courses/{courseId}
  const courseMatch = pathname.match(/\/dashboard\/courses\/([^/]+)/);
  if (!courseMatch) return crumbs;

  const courseId = courseMatch[1];
  const course = courses?.find((c) => c.id === courseId);
  const courseName = course?.name ?? "Course";

  crumbs.push({
    label: courseName,
    href: `/dashboard/courses/${courseId}?tab=overview`,
  });

  // Check for sub-page (e.g., /courses/{id}/revision, /courses/{id}/quizzes/{quizId})
  const subMatch = pathname.match(/\/courses\/[^/]+\/(\w+)/);
  if (subMatch) {
    const segment = subMatch[1];
    const label = SUB_PAGE_LABELS[segment] ?? segment.charAt(0).toUpperCase() + segment.slice(1);
    crumbs.push({ label, href: pathname });
  } else {
    // On main course page, show the active tab
    const tab = searchParams.get("tab");
    if (tab && tab !== "overview") {
      const label = TAB_LABELS[tab] ?? tab;
      crumbs.push({ label, href: `${pathname}?tab=${tab}` });
    }
  }

  return crumbs;
}

export function Navbar({ onMenuClick }: NavbarProps) {
  const breadcrumbs = useBreadcrumbs();
  const pathname = usePathname();
  const isDashboardRoot = pathname === "/dashboard";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--color-border)]/60 bg-[var(--color-surface)] px-4 md:h-16 md:px-8">
      <div className="flex items-center gap-3">
        {/* Mobile hamburger */}
        <button
          onClick={onMenuClick}
          className="rounded-[var(--radius-md)] p-1.5 text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] md:hidden"
          aria-label="Toggle menu"
        >
          <Menu className="size-5" />
        </button>

        {!isDashboardRoot ? (
          <nav
            aria-label="Breadcrumb"
            className="flex items-center gap-1 text-sm"
          >
            {breadcrumbs.map((crumb, index) => {
              const isLast = index === breadcrumbs.length - 1;
              return (
                <span key={crumb.href} className="flex items-center gap-1">
                  {index > 0 && (
                    <ChevronRight className="size-3.5 text-[var(--color-text-muted)]" />
                  )}
                  {isLast ? (
                    <span className="font-medium text-[var(--color-text)]">
                      {crumb.label}
                    </span>
                  ) : (
                    <Link
                      href={crumb.href}
                      className="text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text)]"
                    >
                      {crumb.label}
                    </Link>
                  )}
                </span>
              );
            })}
          </nav>
        ) : (
          <span className="text-xs font-semibold uppercase tracking-[0.22em] text-[var(--color-text-muted)]">
            Meli · Language studio
          </span>
        )}
      </div>

      {/* Language toggle + User button */}
      <div className="flex items-center gap-2">
        <LanguageToggle />
        <UserButton />
      </div>
    </header>
  );
}
