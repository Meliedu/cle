"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, CalendarX2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useSafeError } from "@/hooks/use-safe-error";
import { MemorySummary } from "@/components/memory";
import { useCourse } from "@/hooks/use-courses";
import { useMeetings } from "@/hooks/use-meetings";
import { useDocuments } from "@/hooks/use-documents";
import { useRoster } from "@/hooks/use-enrollment";
import { useCalendar } from "@/hooks/use-calendar";
import { toIsoDate } from "@/components/calendar/calendar-date-math";
import {
  documentReadiness,
  resolveTeachingDay,
  type TeachingEntry,
} from "@/lib/teaching-day";
import {
  courseLifecycle,
  rollUpSources,
  setupIsAvailable,
} from "@/lib/contracts/state";

interface CourseOverviewProps {
  readonly courseId: string;
}

/** Days of sequence the overview shows before deferring to Sessions. */
const WEEK_DAYS = 7;

/**
 * The teacher course overview (Plate 04).
 *
 * What the handoff changed here, rule by rule:
 *
 *   rule 2  Sessions owns the teaching-time spine, so the overview leads to the
 *           next session rather than to a pile of counters.
 *   rule 3  "The next session is the operational hero; publication is quiet
 *           lifecycle context." The old draft banner competed with the data
 *           cards; the lifecycle badge in the page header now carries that,
 *           and Setup is gated by lifecycle rather than permanently present.
 *   rule 4  "The right rail holds readiness, enrollment, source health, and
 *           course memory only." Quick links and the course-access card are
 *           gone: both duplicated destinations that exist elsewhere, and
 *           course access now lives under Students.
 */
export function CourseOverview({ courseId }: CourseOverviewProps) {
  const t = useTranslations("teacher.course.overview");
  const safeError = useSafeError();
  const courseQuery = useCourse(courseId);
  const course = courseQuery.data;

  const now = useMemo(() => new Date(), []);
  const { from, to } = useMemo(() => {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + WEEK_DAYS);
    return { from: toIsoDate(start), to: toIsoDate(end) };
  }, [now]);

  const calendar = useCalendar(courseId, from, to);
  const meetings = useMeetings(courseId);
  const roster = useRoster(courseId);
  const documents = useDocuments(courseId);

  const day = useMemo(() => {
    const events = (calendar.data ?? []).map((event) => ({
      event,
      courseId,
      courseCode: course?.code ?? "",
      courseName: course?.name ?? "",
      colorIndex: 0,
    }));
    return resolveTeachingDay(events, now, { afterLimit: 6 });
  }, [calendar.data, course?.code, course?.name, courseId, now]);

  // The calendar feed is windowed to WEEK_DAYS, so "no class this week" and
  // "no schedule at all" arrive looking identical. The meetings list is not
  // windowed, and this surface already fetches it, so the hero resolves the
  // TRUE next session from it (same resolver, same semantics) rather than
  // telling an instructor with a Sep 1 class to "add a schedule" in August.
  const fallbackNext = useMemo(() => {
    if (day.next || !meetings.data?.length) return null;
    const events = meetings.data
      .filter((meeting) => meeting.status !== "cancelled")
      .map((meeting) => ({
        event: {
          id: meeting.id,
          kind: "meeting" as const,
          title: meeting.title ?? `Session ${meeting.meeting_index}`,
          at: meeting.scheduled_at,
          duration_minutes: meeting.duration_minutes,
          location: meeting.location,
          status: meeting.status,
        },
        courseId,
        courseCode: course?.code ?? "",
        courseName: course?.name ?? "",
        colorIndex: 0,
      }));
    return resolveTeachingDay(events, now).next;
  }, [day.next, meetings.data, course?.code, course?.name, courseId, now]);

  const heroNext = day.next ?? fallbackNext;
  const hasScheduledMeetings = (meetings.data ?? []).some(
    (meeting) => meeting.status !== "cancelled" && Boolean(meeting.scheduled_at)
  );

  const sources = useMemo(
    () =>
      rollUpSources(
        (documents.data ?? []).map((document) =>
          documentReadiness(document.status)
        )
      ),
    [documents.data]
  );

  // `useCourse` returns undefined for BOTH loading and failure (403/404/
  // network). Returning null for both rendered a blank page with no skeleton,
  // no explanation and no way back, while every sibling surface handles this.
  if (courseQuery.isPending) {
    return (
      <div className="space-y-4 p-6" aria-busy="true">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (!course) {
    const safe = safeError.fromError(courseQuery.error);
    return (
      <div className="p-6">
        <StateBanner
          tone="warning"
          title={safe.title}
          reason={safe.consequence}
          action={
            safe.retryable ? (
              <Button
                size="xl"
                variant="outline"
                onClick={() => void courseQuery.refetch()}
              >
                {safe.nextAction}
              </Button>
            ) : undefined
          }
        />
      </div>
    );
  }

  const lifecycle = courseLifecycle(course);
  const studentCount =
    roster.data?.filter((entry) => entry.role === "student").length ?? 0;
  const sessionCount = meetings.data?.length ?? 0;

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-10">
        {/*
          The hero is whichever action is genuinely next. An incomplete course
          has exactly one honest next step, and it is not a session.
        */}
        {setupIsAvailable(lifecycle) ? (
          <SetupHero courseId={courseId} />
        ) : calendar.isLoading || meetings.isLoading ? (
          <Skeleton className="h-[220px] rounded-[var(--radius-2xl)]" />
        ) : heroNext ? (
          <SessionHero
            courseId={courseId}
            entry={heroNext.entry}
            inProgress={heroNext.inProgress}
            isToday={heroNext.isToday}
            sourcesReady={sources.ready}
            sourcesTotal={sources.total}
          />
        ) : hasScheduledMeetings ? (
          // A schedule exists and has run its course. Saying "add a schedule"
          // here would be a false claim; the honest state is "finished".
          <ScheduleEndedHero courseId={courseId} />
        ) : (
          <NoSessionHero courseId={courseId} />
        )}

        <ThisWeek
          courseId={courseId}
          entries={day.afterThis}
          isLoading={calendar.isLoading}
        />
      </div>

      <aside className="space-y-8 lg:border-l lg:border-[var(--color-border)] lg:pl-8">
        <CourseReadiness
          hasClass={heroNext !== null}
          studentCount={studentCount}
          sessionCount={sessionCount}
          sourcesReady={sources.ready}
          sourcesTotal={sources.total}
          isLoading={roster.isLoading || documents.isLoading}
        />

        {/* Course memory self-hides when the course has none reviewed. */}
        <MemorySummary courseId={courseId} />

        <div className="border-t border-[var(--color-border)] pt-5">
          <p className="text-[13px] leading-relaxed text-[var(--color-text-muted)]">
            {t("accessNote")}
          </p>
          <Link
            href={`/teacher/courses/${courseId}/students`}
            className="mt-3 inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-md)] text-[13px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
          >
            {t("openStudents")}
            <ArrowRight aria-hidden="true" className="size-3.5" />
          </Link>
        </div>
      </aside>
    </div>
  );
}

interface SessionHeroProps {
  readonly courseId: string;
  readonly entry: TeachingEntry;
  readonly inProgress: boolean;
  readonly isToday: boolean;
  readonly sourcesReady: number;
  readonly sourcesTotal: number;
}

/** The operational hero: one session, one dominant action. */
function SessionHero({
  courseId,
  entry,
  inProgress,
  isToday,
  sourcesReady,
  sourcesTotal,
}: SessionHeroProps) {
  const t = useTranslations("teacher.course.overview");
  const locale = useLocale();
  const start = new Date(entry.at);

  const lead = inProgress
    ? t("teachingNow")
    : isToday
      ? t("nextTeachingToday", {
          time: start.toLocaleTimeString(locale, {
            hour: "2-digit",
            minute: "2-digit",
          }),
        })
      : t("nextTeachingOn", {
          date: start.toLocaleDateString(locale, {
            weekday: "long",
            day: "numeric",
            month: "short",
          }),
          time: start.toLocaleTimeString(locale, {
            hour: "2-digit",
            minute: "2-digit",
          }),
        });

  const meta = [
    entry.location,
    entry.durationMinutes ? t("minutes", { count: entry.durationMinutes }) : null,
  ].filter((value): value is string => Boolean(value));

  const allReady = sourcesTotal > 0 && sourcesReady === sourcesTotal;

  return (
    <section
      aria-labelledby="course-next-session"
      className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] pl-[5px]"
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[5px] bg-[var(--color-primary)]"
      />
      <div className="flex flex-col gap-6 px-6 py-6 md:px-7 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold tracking-tight text-[var(--color-primary-text)]">
            {lead}
          </p>
          <h2
            id="course-next-session"
            className="mt-2 text-[24px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[27px]"
          >
            {entry.title}
          </h2>
          {meta.length > 0 ? (
            <p className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-[14px] font-medium text-[var(--color-text-secondary)]">
              {meta.map((value) => (
                <span key={value}>{value}</span>
              ))}
            </p>
          ) : null}
          <p
            className={cn(
              "mt-3 inline-flex h-7 items-center rounded-[var(--radius-pill)] border px-3 text-[12px] font-medium",
              allReady
                ? "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]"
                : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]"
            )}
          >
            {sourcesTotal === 0
              ? t("sourcesNone")
              : t("sourcesReady", {
                  ready: sourcesReady,
                  total: sourcesTotal,
                })}
          </p>
        </div>

        <div className="flex shrink-0 flex-col items-start gap-2 lg:items-end">
          <Button
            size="xl"
            render={<Link href={`/teacher/courses/${courseId}/sessions`} />}
          >
            {t("openSession", { title: entry.title })}
          </Button>
          <Link
            href={`/teacher/courses/${courseId}/schedule`}
            className="inline-flex min-h-6 items-center rounded-[var(--radius-sm)] text-[13px] font-medium text-[var(--color-text-secondary)] underline-offset-4 outline-none transition-colors hover:text-[var(--color-text)] hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none pointer-coarse:min-h-11"
          >
            {t("editSession")}
          </Link>
        </div>
      </div>
    </section>
  );
}

/**
 * The hero for an incomplete course.
 *
 * Setup is transient: reachable only while lifecycle is draft or setup, and
 * absent from every navigation surface. This is the one place it is offered,
 * because for an incomplete course it genuinely is the next teaching action.
 */
function SetupHero({ courseId }: { readonly courseId: string }) {
  const t = useTranslations("teacher.course.overview");
  return (
    <section
      aria-labelledby="course-setup-hero"
      className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] pl-[5px]"
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[5px] bg-[var(--color-primary)]"
      />
      <div className="flex flex-col gap-5 px-6 py-6 md:px-7 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h2
            id="course-setup-hero"
            className="text-[22px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)]"
          >
            {t("setupTitle")}
          </h2>
          <p className="mt-1.5 max-w-[60ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("setupReason")}
          </p>
        </div>
        <Button
          size="xl"
          className="shrink-0"
          render={<Link href={`/teacher/courses/${courseId}/setup`} />}
        >
          {t("setupAction")}
        </Button>
      </div>
    </section>
  );
}

/** Published course, nothing scheduled: an intentional state, not a blank. */
/**
 * All scheduled classes are over. Distinct from NoSessionHero on purpose:
 * "add a schedule" is the wrong instruction for a course whose schedule
 * simply finished, and a false claim erodes trust in every other state.
 */
function ScheduleEndedHero({ courseId }: { readonly courseId: string }) {
  const t = useTranslations("teacher.course.overview");
  return (
    <section className="rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border-hover)] bg-[var(--color-surface)] px-6 py-10 text-center">
      <span className="mx-auto flex size-11 items-center justify-center rounded-full bg-[var(--color-bg)]">
        <CalendarX2
          aria-hidden="true"
          strokeWidth={1.6}
          className="size-5 text-[var(--color-text-muted)]"
        />
      </span>
      <h2 className="mt-4 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
        {t("scheduleEndedTitle")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("scheduleEndedReason")}
      </p>
      <Link
        href={`/teacher/courses/${courseId}/schedule`}
        className="mt-5 inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-lg)] px-4 text-[14px] font-medium text-[var(--color-primary-text)] outline-none transition-colors hover:bg-[var(--color-primary-light)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
      >
        {t("scheduleEndedAction")}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Link>
    </section>
  );
}

function NoSessionHero({ courseId }: { readonly courseId: string }) {
  const t = useTranslations("teacher.course.overview");
  return (
    <section className="rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border-hover)] bg-[var(--color-surface)] px-6 py-10 text-center">
      <span className="mx-auto flex size-11 items-center justify-center rounded-full bg-[var(--color-bg)]">
        <CalendarX2
          aria-hidden="true"
          strokeWidth={1.6}
          className="size-5 text-[var(--color-text-muted)]"
        />
      </span>
      <h2 className="mt-4 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
        {t("noSessionTitle")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("noSessionReason")}
      </p>
      <Link
        href={`/teacher/courses/${courseId}/schedule`}
        className="mt-5 inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-lg)] px-4 text-[14px] font-medium text-[var(--color-primary-text)] outline-none transition-colors hover:bg-[var(--color-primary-light)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
      >
        {t("noSessionAction")}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Link>
    </section>
  );
}

interface ThisWeekProps {
  readonly courseId: string;
  readonly entries: readonly TeachingEntry[];
  readonly isLoading: boolean;
}

/**
 * The week's ordered sequence.
 *
 * "One ordered sequence; each release inherits the same sources." Each item
 * appears exactly once (boundary rule 03), carries its own date marker, and
 * states its provenance where the setup rules generated it.
 */
function ThisWeek({ courseId, entries, isLoading }: ThisWeekProps) {
  const t = useTranslations("teacher.course.overview");
  const locale = useLocale();

  return (
    <section aria-labelledby="course-this-week">
      <h2
        id="course-this-week"
        className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
      >
        {t("thisWeek")}
      </h2>
      <p className="mt-1 text-[14px] text-[var(--color-text-secondary)]">
        {t("thisWeekReason")}
      </p>

      {isLoading ? (
        <div className="mt-4 space-y-2">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : entries.length === 0 ? (
        <p className="mt-4 border-t border-[var(--color-border)] pt-4 text-[14px] text-[var(--color-text-muted)]">
          {t("thisWeekEmpty")}
        </p>
      ) : (
        <ol className="mt-4 border-t border-[var(--color-border)]">
          {entries.map((entry) => {
            const at = new Date(entry.at);
            return (
              // The whole row is the link. An adjacent icon-only link would
              // need an accessible name, and repeating the title there would
              // have a screen reader announce every item twice.
              <li key={entry.id} className="border-b border-[var(--color-border)]">
                <Link
                  href={`/teacher/courses/${courseId}/sessions`}
                  className="flex min-h-[68px] items-center gap-4 rounded-[var(--radius-md)] px-2 py-3 outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
                >
                  <span
                    aria-hidden="true"
                    className="flex size-9 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] text-[13px] font-semibold tabular-nums text-[var(--color-text-secondary)]"
                  >
                    {at.getDate()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[15px] font-medium text-[var(--color-text)]">
                      {entry.title}
                    </span>
                    <span className="mt-0.5 block truncate text-[13px] text-[var(--color-text-muted)]">
                      {[
                        at.toLocaleDateString(locale, {
                          weekday: "short",
                          day: "numeric",
                          month: "short",
                        }),
                        at.toLocaleTimeString(locale, {
                          hour: "2-digit",
                          minute: "2-digit",
                        }),
                        entry.location,
                        entry.provenance,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </span>
                  <ArrowRight
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--color-text-muted)]"
                  />
                </Link>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

interface CourseReadinessProps {
  readonly hasClass: boolean;
  readonly studentCount: number;
  readonly sessionCount: number;
  readonly sourcesReady: number;
  readonly sourcesTotal: number;
  readonly isLoading: boolean;
}

/**
 * The right rail: readiness, enrollment, source health.
 *
 * Every number is paired with a word, so the panel reads correctly without
 * color and without the reader inferring meaning from position alone.
 */
function CourseReadiness({
  hasClass,
  studentCount,
  sessionCount,
  sourcesReady,
  sourcesTotal,
  isLoading,
}: CourseReadinessProps) {
  const t = useTranslations("teacher.course.overview");

  const sourcesOk = sourcesTotal > 0 && sourcesReady === sourcesTotal;
  const title = !hasClass
    ? t("noClassTitle")
    : sourcesOk
      ? t("readyTitle")
      : t("notReadyTitle");

  return (
    <section aria-labelledby="course-readiness">
      <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
        {t("readinessLabel")}
      </p>
      <h2
        id="course-readiness"
        className="mt-1 text-[20px] font-semibold leading-snug tracking-[-0.01em] text-[var(--color-text)]"
      >
        {title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("readinessReason")}
      </p>

      {isLoading ? (
        <div className="mt-5 space-y-3">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
        </div>
      ) : (
        <dl className="mt-5">
          <ReadinessStat value={String(studentCount)} label={t("learnersEnrolled")} />
          <ReadinessStat value={String(sessionCount)} label={t("sessionsScheduled")} />
          <ReadinessStat
            value={`${sourcesReady} / ${sourcesTotal}`}
            label={t("sourcesReadyShort")}
            tone={sourcesOk ? "ready" : sourcesTotal === 0 ? "neutral" : "attention"}
          />
        </dl>
      )}
    </section>
  );
}

interface ReadinessStatProps {
  readonly value: string;
  readonly label: string;
  readonly tone?: "neutral" | "ready" | "attention";
}

/**
 * One readiness figure.
 *
 * The value is the `<dd>` and the label is the `<dt>`, which is the correct
 * pairing; `order` puts the number first visually without repeating the label
 * in an sr-only node. Rendering the label twice would make a screen reader
 * announce "learners enrolled" for every stat twice over.
 */
function ReadinessStat({ value, label, tone = "neutral" }: ReadinessStatProps) {
  return (
    <div className="flex items-baseline gap-3 border-b border-[var(--color-border)] py-3">
      <dd
        className={cn(
          "order-1 text-[22px] font-semibold tabular-nums tracking-tight",
          tone === "ready"
            ? "text-[var(--color-success)]"
            : tone === "attention"
              ? "text-[var(--color-primary-text)]"
              : "text-[var(--color-text)]"
        )}
      >
        {value}
      </dd>
      <dt className="order-2 text-[13px] text-[var(--color-text-secondary)]">
        {label}
      </dt>
    </div>
  );
}
