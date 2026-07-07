"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, ClipboardList } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import {
  useCheckpoints,
  useCheckpointHistory,
  type Checkpoint,
} from "@/hooks/use-checkpoints";

import {
  StatusChip,
  releaseTone,
  checkpointTone,
  primaryCheckpoint,
  groupByMeeting,
} from "./session-status";

interface SessionsListProps {
  readonly courseId: string;
}

/** A session is "done" once completed/archived or taught/cancelled. */
function isCompleted(meeting: Meeting): boolean {
  return (
    meeting.release_state === "completed" ||
    meeting.release_state === "archived" ||
    meeting.status === "taught" ||
    meeting.status === "cancelled"
  );
}

/** Split a scheduled_at ISO into a compact day-badge (e.g. "26 JUN"). */
function dayBadge(iso: string): { readonly day: string; readonly month: string } {
  const date = new Date(iso);
  return {
    day: date.toLocaleDateString(undefined, { day: "2-digit" }),
    month: date
      .toLocaleDateString(undefined, { month: "short" })
      .toUpperCase(),
  };
}

/** Locale time for a session, e.g. "10:30". */
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * T037 — teacher sessions list. Joins the P1 meetings (`useMeetings`) with their
 * checkpoints (draft via `useCheckpoints` + closed via `useCheckpointHistory`),
 * grouping checkpoints by `meeting_id`. Each session shows its student-visibility
 * `release_state` and a one-chip checkpoint summary, and drills into the session
 * detail. Sessions split into active vs completed groups. Session/checkpoint
 * creation still lives in setup, linked from the header.
 */
export function SessionsList({ courseId }: SessionsListProps) {
  const t = useTranslations("teacher.sessions");
  const { data: meetingsData, isLoading } = useMeetings(courseId);
  const { data: draftCheckpoints } = useCheckpoints(courseId);
  const { data: historyCheckpoints } = useCheckpointHistory(courseId);

  const setupHref = `/teacher/courses/${courseId}/setup`;

  const allCheckpoints: readonly Checkpoint[] = [
    ...(draftCheckpoints ?? []),
    ...(historyCheckpoints ?? []),
  ];
  const byMeeting = groupByMeeting(allCheckpoints);

  const meetings: readonly Meeting[] = meetingsData
    ? [...meetingsData].sort((a, b) => a.meeting_index - b.meeting_index)
    : [];
  const active = meetings.filter((m) => !isCompleted(m));
  const completed = meetings.filter(isCompleted);

  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <Button size="sm" variant="outline" render={<Link href={setupHref} />}>
          {t("manageInSetup")}
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton
              key={i}
              className="h-[68px] w-full rounded-[var(--radius-xl)]"
            />
          ))}
        </div>
      ) : meetings.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={t("empty.title")}
          reason={t("empty.reason")}
          action={
            <Button
              size="sm"
              variant="outline"
              render={<Link href={setupHref} />}
            >
              {t("manageInSetup")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-8">
          <SessionGroup
            heading={t("groups.active")}
            emptyLabel={t("groups.activeEmpty")}
            meetings={active}
            courseId={courseId}
            byMeeting={byMeeting}
          />
          {completed.length > 0 ? (
            <SessionGroup
              heading={t("groups.completed")}
              meetings={completed}
              courseId={courseId}
              byMeeting={byMeeting}
            />
          ) : null}
        </div>
      )}
    </section>
  );
}

interface SessionGroupProps {
  readonly heading: string;
  readonly emptyLabel?: string;
  readonly meetings: readonly Meeting[];
  readonly courseId: string;
  readonly byMeeting: ReadonlyMap<string, readonly Checkpoint[]>;
}

function SessionGroup({
  heading,
  emptyLabel,
  meetings,
  courseId,
  byMeeting,
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
            <SessionRow
              key={m.id}
              meeting={m}
              courseId={courseId}
              checkpoints={byMeeting.get(m.id) ?? []}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

interface SessionRowProps {
  readonly meeting: Meeting;
  readonly courseId: string;
  readonly checkpoints: readonly Checkpoint[];
}

function SessionRow({ meeting, courseId, checkpoints }: SessionRowProps) {
  const t = useTranslations("teacher.sessions");
  const href = `/teacher/courses/${courseId}/sessions/${meeting.id}`;
  const { day, month } = dayBadge(meeting.scheduled_at);
  const topic = meeting.topic_summary || meeting.title || t("untitled");
  const primary = primaryCheckpoint(checkpoints);

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

        <div className="hidden shrink-0 items-center gap-2 sm:flex">
          {primary ? (
            <StatusChip
              tone={checkpointTone(primary.status)}
              label={
                checkpoints.length > 1
                  ? t("checkpointCount", { count: checkpoints.length })
                  : t(`checkpointStatus.${primary.status}`)
              }
            />
          ) : (
            <StatusChip tone="muted" label={t("noCheckpoint")} />
          )}
        </div>

        <ArrowRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5"
        />
      </Link>
    </li>
  );
}
