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

// Human labels for path/tab segments across both the legacy `/dashboard/*` and
// the role-scoped `/teacher/*` · `/student/*` route trees.
const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  courses: "Courses",
  calendar: "Calendar",
  insights: "Insights",
  profile: "Profile",
  notifications: "Notifications",
  new: "New course",
  overview: "Overview",
  sessions: "Sessions",
  schedule: "Schedule",
  enrollment: "Enrollment",
  setup: "Course setup",
  materials: "Materials",
  activities: "Activities",
  checklist: "Checklist",
  reports: "Reports",
  memory: "Course memory",
  join: "Join a course",
  quizzes: "Quizzes",
  flashcards: "Flashcards",
  revision: "Revision",
  pronunciation: "Pronunciation",
  live: "Live Quiz",
  progress: "Progress",
  leaderboard: "Leaderboard",
  students: "Students",
};

function labelFor(segment: string): string {
  return (
    SEGMENT_LABELS[segment] ??
    segment.charAt(0).toUpperCase() + segment.slice(1).replace(/-/g, " ")
  );
}

interface Crumb {
  label: string;
  href: string;
}

function useBreadcrumbs(): readonly Crumb[] {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: courses } = useCourses();

  const segments = pathname.split("/").filter(Boolean);
  const lane = segments[0];

  // Role-scoped route trees: /teacher/* and /student/*.
  if (lane === "teacher" || lane === "student") {
    const home = `/${lane}/dashboard`;
    const crumbs: Crumb[] = [{ label: "Dashboard", href: home }];
    const section = segments[1];
    if (!section || section === "dashboard") return crumbs;

    if (section === "courses") {
      crumbs.push({ label: "Courses", href: `/${lane}/courses` });
      const third = segments[2];
      if (third === "new") {
        crumbs.push({ label: "New course", href: pathname });
      } else if (third) {
        const course = courses?.find((c) => c.id === third);
        crumbs.push({
          label: course?.name ?? "Course",
          href: `/${lane}/courses/${third}`,
        });
        if (segments[3]) {
          crumbs.push({ label: labelFor(segments[3]), href: pathname });
        }
      }
      return crumbs;
    }

    crumbs.push({ label: labelFor(section), href: `/${lane}/${section}` });
    return crumbs;
  }

  // Legacy `/dashboard/*` fallback (kept until those routes are retired).
  const crumbs: Crumb[] = [{ label: "Dashboard", href: "/dashboard" }];
  const courseMatch = pathname.match(/\/dashboard\/courses\/([^/]+)/);
  if (!courseMatch) return crumbs;

  const courseId = courseMatch[1];
  const course = courses?.find((c) => c.id === courseId);
  crumbs.push({
    label: course?.name ?? "Course",
    href: `/dashboard/courses/${courseId}?tab=overview`,
  });

  const subMatch = pathname.match(/\/courses\/[^/]+\/(\w+)/);
  if (subMatch) {
    crumbs.push({ label: labelFor(subMatch[1]), href: pathname });
  } else {
    const tab = searchParams.get("tab");
    if (tab && tab !== "overview") {
      crumbs.push({ label: labelFor(tab), href: `${pathname}?tab=${tab}` });
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
            Meli · HKUST CLE
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
