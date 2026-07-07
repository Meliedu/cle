"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, FolderOpen } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { StatusChip, releaseTone } from "@/components/course/session-status";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";

interface StudentSessionsListProps {
  readonly courseId: string;
}

/** Students only see sessions their instructor has released (or completed). */
function isVisible(meeting: Meeting): boolean {
  return (
    meeting.release_state === "released" ||
    meeting.release_state === "completed"
  );
}

/** A completed session sorts into its own group. */
function isCompleted(meeting: Meeting): boolean {
  return meeting.release_state === "completed";
}

/** Compact day badge, e.g. { day: "10", month: "JUL" }. */
function dayBadge(iso: string): { readonly day: string; readonly month: string } {
  const date = new Date(iso);
  return {
    day: date.toLocaleDateString(undefined, { day: "2-digit" }),
    month: date.toLocaleDateString(undefined, { month: "short" }).toUpperCase(),
  };
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * S026 — student sessions list. Shows only the sessions the instructor has
 * released (or completed); locked/archived sessions stay hidden here (they
 * still appear on the class schedule with a "not yet open" status). Rows drill
 * into the session detail. Active vs completed are split into two groups.
 */
export function StudentSessionsList({ courseId }: StudentSessionsListProps) {
  const t = useTranslations("student.sessions");
  const { data, isLoading, isError } = useMeetings(courseId);

  const { active, completed } = useMemo(() => {
    const visible = (data ?? [])
      .filter(isVisible)
      .sort((a, b) => a.meeting_index - b.meeting_index);
    return {
      active: visible.filter((m) => !isCompleted(m)),
      completed: visible.filter(isCompleted),
    };
  }, [data]);

  if (isError) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px] w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (active.length === 0 && completed.length === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  return (
    <section className="space-y-8">
      <SessionGroup
        heading={t("groups.active")}
        emptyLabel={t("groups.activeEmpty")}
        meetings={active}
        courseId={courseId}
      />
      {completed.length > 0 ? (
        <SessionGroup
          heading={t("groups.completed")}
          meetings={completed}
          courseId={courseId}
        />
      ) : null}
    </section>
  );
}

interface SessionGroupProps {
  readonly heading: string;
  readonly emptyLabel?: string;
  readonly meetings: readonly Meeting[];
  readonly courseId: string;
}

function SessionGroup({
  heading,
  emptyLabel,
  meetings,
  courseId,
}: SessionGroupProps) {
  return (
    <div className="space-y-3">
      <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {heading}
      </h3>
      {meetings.length === 0 ? (
        emptyLabel ? (
          <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-[13px] text-[var(--color-text-muted)]">
            {emptyLabel}
          </p>
        ) : null
      ) : (
        <ul className="space-y-2">
          {meetings.map((m) => (
            <SessionRow key={m.id} meeting={m} courseId={courseId} />
          ))}
        </ul>
      )}
    </div>
  );
}

function SessionRow({
  meeting,
  courseId,
}: {
  readonly meeting: Meeting;
  readonly courseId: string;
}) {
  const t = useTranslations("student.sessions");
  const href = `/student/courses/${courseId}/sessions/${meeting.id}`;
  const { day, month } = dayBadge(meeting.scheduled_at);
  const topic = meeting.topic_summary || meeting.title || t("untitled");

  return (
    <li>
      <Link
        href={href}
        className="group flex items-center gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]"
      >
        <div className="flex size-12 shrink-0 flex-col items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
          <span className="text-[15px] font-bold leading-none">{day}</span>
          <span className="mt-0.5 text-[10px] font-semibold tracking-wide">
            {month}
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("sessionLabel", { index: meeting.meeting_index })}
            </span>
            <StatusChip
              tone={releaseTone(meeting.release_state)}
              label={t(`release.${meeting.release_state}`)}
            />
          </div>
          <p className="truncate text-[14px] font-semibold text-[var(--color-text)]">
            {topic}
          </p>
          <p className="truncate text-[12px] text-[var(--color-text-muted)]">
            {formatTime(meeting.scheduled_at)}
            {meeting.location ? ` · ${meeting.location}` : ""}
          </p>
        </div>

        <ArrowRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5"
        />
      </Link>
    </li>
  );
}
