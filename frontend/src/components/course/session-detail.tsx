"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  CalendarClock,
  ClipboardList,
  MapPin,
  Pencil,
  Timer,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import {
  useCheckpoints,
  useCheckpointHistory,
  type Checkpoint,
} from "@/hooks/use-checkpoints";

import { StatusChip, releaseTone, checkpointTone } from "./session-status";
import { AttendanceRoster } from "./attendance-roster";

interface SessionDetailProps {
  readonly courseId: string;
  readonly meetingId: string;
}

/** Full date + time for the session header, e.g. "Fri, 26 Jun · 10:30". */
function formatWhen(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${day} · ${time}`;
}

/**
 * T038 — teacher session detail. Reads the session from `useMeetings` (no single
 * meeting GET exists) and its checkpoints from `useCheckpoints` +
 * `useCheckpointHistory`, filtered by `meeting_id`. Shows the session facts
 * (when / venue / duration / topic) with its release-state chip, and the
 * session's checkpoint(s) each linking into the checkpoint studio (T17). Editing
 * the session + its release state lives one route deeper (`/edit`, T039).
 */
export function SessionDetail({ courseId, meetingId }: SessionDetailProps) {
  const t = useTranslations("teacher.sessions");
  const { data: meetingsData, isLoading } = useMeetings(courseId);
  const { data: draftCheckpoints } = useCheckpoints(courseId);
  const { data: historyCheckpoints } = useCheckpointHistory(courseId);

  const listHref = `/teacher/courses/${courseId}/sessions`;
  const editHref = `${listHref}/${meetingId}/edit`;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  const meeting = meetingsData?.find((m) => m.id === meetingId);
  if (!meeting) {
    return (
      <StateBanner
        tone="warning"
        title={t("notFound.title")}
        reason={t("notFound.reason")}
        action={
          <Button size="sm" variant="outline" render={<Link href={listHref} />}>
            {t("backToList")}
          </Button>
        }
      />
    );
  }

  const checkpoints: readonly Checkpoint[] = [
    ...(draftCheckpoints ?? []),
    ...(historyCheckpoints ?? []),
  ].filter((cp) => cp.meeting_id === meetingId);

  const title = meeting.topic_summary || meeting.title || t("untitled");

  return (
    <div className="space-y-6">
      <Link
        href={listHref}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        {t("backToList")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("sessionLabel", { index: meeting.meeting_index })}
            </span>
            <StatusChip
              tone={releaseTone(meeting.release_state)}
              label={t(`release.${meeting.release_state}`)}
            />
          </div>
          <h2 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
            {title}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {formatWhen(meeting.scheduled_at)}
          </p>
        </div>
        <Button variant="default" size="sm" render={<Link href={editHref} />}>
          <Pencil aria-hidden="true" />
          {t("editSession")}
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <FactCard
          icon={CalendarClock}
          label={t("facts.when")}
          value={formatWhen(meeting.scheduled_at)}
        />
        <FactCard
          icon={MapPin}
          label={t("facts.venue")}
          value={meeting.location || t("placeholder")}
        />
        <FactCard
          icon={Timer}
          label={t("facts.duration")}
          value={t("facts.minutes", { count: meeting.duration_minutes })}
        />
      </div>

      <CheckpointPanel
        courseId={courseId}
        meetingId={meetingId}
        checkpoints={checkpoints}
        meeting={meeting}
      />

      <section className="space-y-3">
        <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
          {t("attendance.title")}
        </h3>
        <AttendanceRoster meetingId={meetingId} />
      </section>
    </div>
  );
}

interface FactCardProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly value: string;
}

function FactCard({ icon: Icon, label, value }: FactCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </p>
        <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
          {value}
        </p>
      </div>
    </div>
  );
}

interface CheckpointPanelProps {
  readonly courseId: string;
  readonly meetingId: string;
  readonly checkpoints: readonly Checkpoint[];
  readonly meeting: Meeting;
}

function CheckpointPanel({
  courseId,
  meetingId,
  checkpoints,
  meeting,
}: CheckpointPanelProps) {
  const t = useTranslations("teacher.sessions");
  const studioBase = `/teacher/courses/${courseId}/sessions/${meetingId}/checkpoints`;

  return (
    <section className="space-y-3">
      <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
        {t("checkpoints.title")}
      </h3>

      {checkpoints.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={t("checkpoints.emptyTitle")}
          reason={
            meeting.release_state === "locked"
              ? t("checkpoints.emptyLocked")
              : t("checkpoints.emptyReason")
          }
        />
      ) : (
        <ul className="space-y-2">
          {checkpoints.map((cp) => (
            <li key={cp.id}>
              <Link
                href={`${studioBase}/${cp.id}`}
                className="group flex items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 transition-colors hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]"
              >
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
                    {cp.title}
                  </p>
                  <p className="text-[12px] text-[var(--color-text-muted)]">
                    {t("checkpoints.openStudio")}
                  </p>
                </div>
                <StatusChip
                  tone={checkpointTone(cp.status)}
                  label={t(`checkpointStatus.${cp.status}`)}
                />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
