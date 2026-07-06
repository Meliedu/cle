"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CalendarClock,
  CalendarPlus,
  Check,
  Eye,
  EyeOff,
  FolderPlus,
  Loader2,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/patterns";
import {
  useMeetings,
  useSetMeetingReleaseState,
  useUpdateMeeting,
  type Meeting,
} from "@/hooks/use-meetings";

interface StepSessionsProps {
  readonly courseId: string;
  /** Back to the schedule editor (T018) to add or remove sessions. */
  readonly onEdit?: () => void;
  /** Advance past the session review (informational — folds under `schedule`). */
  readonly onComplete?: () => void;
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * T021 — session-generation-review step. A read-only review gate over the
 * sessions produced in the schedule step (T018): the teacher confirms each
 * generated session and can still tweak its `topic_summary` or `release_state`
 * inline before approving. There is NO distinct `SETUP_STEP_KEYS` entry for this
 * screen — it folds under `schedule` (already flagged by the editor), so
 * "Approve sessions" is informational and just advances the wizard.
 */
export function StepSessions({ courseId, onEdit, onComplete }: StepSessionsProps) {
  const t = useTranslations("teacher.setup.sessions");
  const { data: meetings, isLoading } = useMeetings(courseId);
  const [actionError, setActionError] = useState<string | null>(null);

  const sessions = useMemo(
    () => [...(meetings ?? [])].sort((a, b) => a.meeting_index - b.meeting_index),
    [meetings]
  );
  const hasSessions = sessions.length > 0;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        <section aria-label={t("listLabel")} className="space-y-2.5">
          {isLoading ? (
            <EmptyState variant="waiting" title={t("loading")} />
          ) : !hasSessions ? (
            <EmptyState
              variant="empty"
              icon={CalendarClock}
              title={t("empty.title")}
              reason={t("empty.reason")}
            />
          ) : (
            <ul className="space-y-2.5">
              {sessions.map((meeting) => (
                <SessionRow
                  key={meeting.id}
                  courseId={courseId}
                  meeting={meeting}
                  onError={setActionError}
                  t={t}
                />
              ))}
            </ul>
          )}
        </section>

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={!hasSessions}
            onClick={() => onComplete?.()}
          >
            {t("approve")}
          </Button>
          {onEdit ? (
            <Button type="button" size="sm" variant="ghost" onClick={() => onEdit()}>
              {t("edit")}
            </Button>
          ) : null}
        </div>
      </div>

      <AfterApprovalAside t={t} />
    </div>
  );
}

interface SessionRowProps {
  readonly courseId: string;
  readonly meeting: Meeting;
  readonly onError: (message: string | null) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function SessionRow({ courseId, meeting, onError, t }: SessionRowProps) {
  const updateMeeting = useUpdateMeeting(courseId);
  const setReleaseState = useSetMeetingReleaseState(courseId);
  const [topic, setTopic] = useState(meeting.topic_summary ?? "");
  const [editing, setEditing] = useState(false);

  const released = meeting.release_state === "released";

  const saveTopic = useCallback(async () => {
    onError(null);
    try {
      await updateMeeting.mutateAsync({
        meetingId: meeting.id,
        patch: { topic_summary: topic.trim() || null },
      });
      setEditing(false);
    } catch {
      onError(t("saveError"));
    }
  }, [updateMeeting, meeting.id, topic, onError, t]);

  const toggleRelease = useCallback(async () => {
    onError(null);
    if (meeting.release_state !== "locked" && meeting.release_state !== "released") return;
    const target = released ? "locked" : "released";
    try {
      await setReleaseState.mutateAsync({ meetingId: meeting.id, releaseState: target });
    } catch {
      onError(t("releaseError"));
    }
  }, [setReleaseState, meeting.id, meeting.release_state, released, onError, t]);

  return (
    <li className="space-y-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <p className="text-[13px] font-semibold text-[var(--color-text)]">
            {t("sessionLabel", { index: meeting.meeting_index })}
          </p>
          <p className="flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)]">
            <CalendarClock aria-hidden="true" className="size-3.5 shrink-0" />
            {formatWhen(meeting.scheduled_at)}
            {meeting.location ? ` · ${meeting.location}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant={released ? "secondary" : "outline"}>
            {released ? t("released") : t("locked")}
          </Badge>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            aria-label={released ? t("lock") : t("release")}
            disabled={setReleaseState.isPending}
            onClick={() => void toggleRelease()}
          >
            {released ? (
              <Eye aria-hidden="true" className="text-[var(--color-success)]" />
            ) : (
              <EyeOff aria-hidden="true" />
            )}
          </Button>
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          <Textarea
            aria-label={t("topicLabel", { index: meeting.meeting_index })}
            rows={2}
            value={topic}
            placeholder={t("topicPlaceholder")}
            onChange={(e) => setTopic(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              disabled={updateMeeting.isPending}
              onClick={() => void saveTopic()}
            >
              {updateMeeting.isPending ? (
                <Loader2 aria-hidden="true" className="animate-spin" />
              ) : (
                <Check aria-hidden="true" />
              )}
              {t("saveTopic")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setTopic(meeting.topic_summary ?? "");
                setEditing(false);
              }}
            >
              {t("cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="w-full rounded-[var(--radius-sm)] text-left text-[12px] leading-relaxed text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
        >
          {meeting.topic_summary || t("topicEmpty")}
        </button>
      )}
    </li>
  );
}

function AfterApprovalAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const items = [
    { icon: FolderPlus, key: "folders" },
    { icon: CalendarPlus, key: "calendar" },
    { icon: Sparkles, key: "checkpoints" },
  ] as const;

  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <ul className="mt-4 space-y-4">
        {items.map(({ icon: Icon, key }) => (
          <li key={key} className="flex gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
              <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
            </span>
            <div className="min-w-0 space-y-0.5">
              <p className="text-[13px] font-medium text-[var(--color-text)]">
                {t(`aside.${key}.title`)}
              </p>
              <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
                {t(`aside.${key}.description`)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
