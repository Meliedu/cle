"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, CheckCircle2, Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { useNextAction, type ChecklistItem } from "@/hooks/use-work-items";
import { useDashboardPreviewEvents } from "@/components/dashboard/dashboard-preview-events";
import { WelcomeHero } from "@/components/dashboard/welcome-hero";
import { TodoList } from "@/components/dashboard/todo-list";
import { MiniCalendar } from "@/components/dashboard/mini-calendar";
import { UpcomingSwarms } from "@/components/dashboard/upcoming-swarms";
import { RecentCourses } from "@/components/dashboard/recent-courses";

/**
 * Dashboard overview composition shared by every role lane
 * (`/teacher/dashboard`, `/student/dashboard`, and the legacy `/dashboard`
 * before it redirects). Both roles render a near-identical overview today;
 * later phases differentiate the panels per role.
 */
export function DashboardHome() {
  const { data: courses, isLoading } = useCourses();
  const events = useDashboardPreviewEvents();
  const [selected, setSelected] = useState<Date | undefined>(new Date());

  const courseList: readonly CourseResponse[] = useMemo(
    () => courses ?? [],
    [courses]
  );

  // The next-action spine read is per-course (Decision 7). The dashboard is
  // multi-course, so we surface the MOST RELEVANT course's next action — the
  // most recently updated course the user can see. `useNextAction` stays
  // disabled (empty id) until a course exists.
  const activeCourseId = useMemo(() => {
    if (courseList.length === 0) return "";
    return [...courseList].sort((a, b) =>
      b.updated_at.localeCompare(a.updated_at)
    )[0].id;
  }, [courseList]);

  if (isLoading) return <DashboardSkeleton />;

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 px-6 py-6 md:px-10 md:py-10">
      <WelcomeHero />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column (2/3) — next action + to-do + recent courses */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          <NextActionCard courseId={activeCourseId} />
          <TodoList />
          <RecentCourses courses={courseList} />
        </div>

        {/* Right column (1/3) — mini calendar + upcoming */}
        <div className="flex flex-col gap-6">
          <MiniCalendar
            events={events}
            selected={selected}
            onSelectDate={setSelected}
          />
          <UpcomingSwarms
            events={events}
            title="Upcoming sessions"
            showPreviewBadge={false}
            emptyLabel="No sessions scheduled yet."
          />
        </div>
      </div>
    </div>
  );
}

interface NextActionCardProps {
  readonly courseId: string;
}

/**
 * F9 — the dashboard next-action slot, fed from the work-item spine
 * (`useNextAction`, Decision 7 — NOT the localStorage `use-todos` widget, which
 * stays). Shows the single soonest pending/in-progress task with its due date
 * and a link into the course; when the checklist is clear it shows a designed
 * "all caught up" state. Renders nothing while the query is idle/disabled or for
 * callers the spine doesn't serve (e.g. a teacher who isn't enrolled → 403).
 */
function NextActionCard({ courseId }: NextActionCardProps) {
  const t = useTranslations("student.dashboard.nextAction");
  const locale = useLocale();
  const { data, isLoading, isSuccess } = useNextAction(courseId);

  if (!courseId) return null;

  if (isLoading) {
    return <Skeleton className="h-[104px] rounded-[var(--radius-2xl)]" />;
  }

  if (!isSuccess) return null;

  if (data === null || data === undefined) {
    return (
      <section className="flex items-center gap-3 rounded-[var(--radius-2xl)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] px-5 py-4">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface)]">
          <CheckCircle2
            aria-hidden="true"
            strokeWidth={1.85}
            className="size-5 text-[var(--color-success)]"
          />
        </span>
        <div className="min-w-0">
          <p className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("clearTitle")}
          </p>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("clearReason")}
          </p>
        </div>
      </section>
    );
  }

  return <NextActionItem item={data} courseId={courseId} locale={locale} t={t} />;
}

interface NextActionItemProps {
  readonly item: ChecklistItem;
  readonly courseId: string;
  readonly locale: string;
  readonly t: ReturnType<typeof useTranslations>;
}

function NextActionItem({ item, courseId, locale, t }: NextActionItemProps) {
  // Checkpoints have a dedicated student route today; other sources open the
  // course workspace (added this phase). Keeps the CTA on a real destination.
  const href =
    item.source_kind === "checkpoint"
      ? `/student/courses/${courseId}/checkpoints`
      : `/student/courses/${courseId}`;

  const dueLabel = item.due_at
    ? t("due", {
        date: new Date(item.due_at).toLocaleDateString(locale, {
          weekday: "short",
          day: "numeric",
          month: "short",
        }),
      })
    : t("noDue");

  return (
    <section className="flex flex-wrap items-center gap-4 rounded-[var(--radius-2xl)] border border-[var(--color-primary)]/30 bg-[var(--color-primary-light)] px-5 py-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-surface)]">
        <Target
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-5 text-[var(--color-primary-hover)]"
        />
      </span>

      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-primary-hover)]">
          {t("eyebrow")}
        </p>
        <p className="mt-0.5 truncate text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {item.title}
        </p>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-[var(--color-text-secondary)]">
          <span>{t(`source.${item.source_kind}`)}</span>
          <span aria-hidden="true">·</span>
          <span>{dueLabel}</span>
          <span aria-hidden="true">·</span>
          <span>{item.required ? t("required") : t("optional")}</span>
        </p>
      </div>

      <Button size="sm" render={<Link href={href} />}>
        {t("open")}
        <ArrowRight aria-hidden="true" />
      </Button>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 px-6 py-6 md:px-10 md:py-10">
      <div className="space-y-3 border-b border-[var(--color-border)]/70 pb-6">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Skeleton className="h-[420px] rounded-[var(--radius-2xl)]" />
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-[var(--radius-2xl)]" />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-6">
          <Skeleton className="h-[340px] rounded-[var(--radius-2xl)]" />
          <Skeleton className="h-[260px] rounded-[var(--radius-2xl)]" />
        </div>
      </div>
    </div>
  );
}
