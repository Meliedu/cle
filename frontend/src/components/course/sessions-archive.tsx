"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, ArrowRight, Archive, ClipboardCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import {
  useCheckpointHistory,
  type Checkpoint,
} from "@/hooks/use-checkpoints";

import { StatusChip, checkpointTone, releaseTone } from "./session-status";

interface SessionsArchiveProps {
  readonly courseId: string;
}

/** Completed / archived sessions only — the taught-and-done half of the term. */
function isArchivedSession(meeting: Meeting): boolean {
  return (
    meeting.release_state === "completed" ||
    meeting.release_state === "archived" ||
    meeting.status === "taught" ||
    meeting.status === "cancelled"
  );
}

/** Compact date for an archived row, e.g. "26 Jun 2026". */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * T049 + T050 + T051 — checkpoint history + completed-sessions archive. The
 * read-only "what already happened" view of a course: every closed/archived
 * checkpoint (each linking back into its results in the studio) and every
 * completed/archived session. When neither exists yet it renders one designed
 * waiting EmptyState (reason + a route back to the active sessions), never a
 * blank region.
 */
export function SessionsArchive({ courseId }: SessionsArchiveProps) {
  const t = useTranslations("teacher.history");
  const { data: meetingsData, isLoading: meetingsLoading } = useMeetings(courseId);
  const { data: historyData, isLoading: historyLoading } =
    useCheckpointHistory(courseId);

  const sessionsHref = `/teacher/courses/${courseId}/sessions`;

  const checkpoints: readonly Checkpoint[] = historyData ?? [];
  const archivedSessions: readonly Meeting[] = (meetingsData ?? [])
    .filter(isArchivedSession)
    .sort((a, b) => b.meeting_index - a.meeting_index);

  const isLoading = meetingsLoading || historyLoading;

  return (
    <div className="space-y-6">
      <Link
        href={sessionsHref}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        {t("back")}
      </Link>

      <div className="space-y-1">
        <h2 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="max-w-[60ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton
              key={i}
              className="h-[60px] w-full rounded-[var(--radius-xl)]"
            />
          ))}
        </div>
      ) : checkpoints.length === 0 && archivedSessions.length === 0 ? (
        <EmptyState
          variant="waiting"
          title={t("empty.title")}
          reason={t("empty.reason")}
          action={
            <Button size="sm" variant="outline" render={<Link href={sessionsHref} />}>
              {t("empty.action")}
            </Button>
          }
        />
      ) : (
        <div className="space-y-8">
          <section className="space-y-3">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("checkpointsHeading")}
            </h3>
            {checkpoints.length === 0 ? (
              <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-[13px] text-[var(--color-text-muted)]">
                {t("noCheckpoints")}
              </p>
            ) : (
              <ul className="space-y-2">
                {checkpoints.map((cp) => (
                  <CheckpointHistoryRow
                    key={cp.id}
                    courseId={courseId}
                    checkpoint={cp}
                  />
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-3">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("sessionsHeading")}
            </h3>
            {archivedSessions.length === 0 ? (
              <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-[13px] text-[var(--color-text-muted)]">
                {t("noSessions")}
              </p>
            ) : (
              <ul className="space-y-2">
                {archivedSessions.map((meeting) => (
                  <ArchivedSessionRow
                    key={meeting.id}
                    courseId={courseId}
                    meeting={meeting}
                  />
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

interface CheckpointHistoryRowProps {
  readonly courseId: string;
  readonly checkpoint: Checkpoint;
}

function CheckpointHistoryRow({ courseId, checkpoint }: CheckpointHistoryRowProps) {
  const t = useTranslations("teacher.history");
  const href = checkpoint.meeting_id
    ? `/teacher/courses/${courseId}/sessions/${checkpoint.meeting_id}/checkpoints/${checkpoint.id}`
    : null;

  const body = (
    <>
      <div className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
        <ClipboardCheck aria-hidden="true" strokeWidth={1.85} className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
          {checkpoint.title}
        </p>
        <p className="text-[12px] text-[var(--color-text-muted)]">
          {href ? t("viewResults") : t("noSessionLink")}
        </p>
      </div>
      <StatusChip
        tone={checkpointTone(checkpoint.status)}
        label={t(`status.${checkpoint.status}`)}
      />
    </>
  );

  const rowClass =
    "flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3";

  if (!href) {
    return <li className={rowClass}>{body}</li>;
  }

  return (
    <li>
      <Link
        href={href}
        className={`group ${rowClass} transition-colors hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]`}
      >
        {body}
        <ArrowRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5"
        />
      </Link>
    </li>
  );
}

interface ArchivedSessionRowProps {
  readonly courseId: string;
  readonly meeting: Meeting;
}

function ArchivedSessionRow({ courseId, meeting }: ArchivedSessionRowProps) {
  const t = useTranslations("teacher.history");
  const ts = useTranslations("teacher.sessions");
  const href = `/teacher/courses/${courseId}/sessions/${meeting.id}`;
  const title = meeting.topic_summary || meeting.title || t("untitled");

  return (
    <li>
      <Link
        href={href}
        className="group flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 transition-colors hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]"
      >
        <div className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
          <Archive aria-hidden="true" strokeWidth={1.85} className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
            {title}
          </p>
          <p className="text-[12px] text-[var(--color-text-muted)]">
            {formatDate(meeting.scheduled_at)}
          </p>
        </div>
        <StatusChip
          tone={releaseTone(meeting.release_state)}
          label={ts(`release.${meeting.release_state}`)}
        />
        <ArrowRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5"
        />
      </Link>
    </li>
  );
}
