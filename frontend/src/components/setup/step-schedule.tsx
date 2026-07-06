"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CalendarClock,
  Eye,
  EyeOff,
  Loader2,
  MapPin,
  Pencil,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/patterns";
import {
  useCreateMeeting,
  useDeleteMeeting,
  useMeetings,
  useSetMeetingReleaseState,
  useUpdateMeeting,
  type Meeting,
} from "@/hooks/use-meetings";
import { useSetStep } from "@/hooks/use-setup";

interface StepScheduleProps {
  readonly courseId: string;
  /** Fired after the `schedule` checklist flag is set. */
  readonly onComplete?: () => void;
}

interface SessionDraft {
  readonly meetingIndex: string;
  readonly scheduledAt: string;
  readonly durationMinutes: string;
  readonly location: string;
  readonly topicSummary: string;
}

const EMPTY_DRAFT: SessionDraft = {
  meetingIndex: "",
  scheduledAt: "",
  durationMinutes: "60",
  location: "",
  topicSummary: "",
};

/** ISO datetime → the `datetime-local` input value (`YYYY-MM-DDTHH:mm`). */
function toLocalInput(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/**
 * T018 — schedule-and-venue step. Reuses the existing `meetings.py` router
 * (`useMeetings` + create/update/delete + the Task 7 release-state control) to
 * list, add, edit, and release course sessions with a session number
 * (`meeting_index`), date/time, venue (`location`), duration, and a topic
 * summary. Flips the `schedule` checklist flag once at least one session exists.
 */
export function StepSchedule({ courseId, onComplete }: StepScheduleProps) {
  const t = useTranslations("teacher.setup.schedule");
  const { data: meetings, isLoading } = useMeetings(courseId);
  const createMeeting = useCreateMeeting(courseId);
  const updateMeeting = useUpdateMeeting(courseId);
  const deleteMeeting = useDeleteMeeting(courseId);
  const setStep = useSetStep(courseId);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<SessionDraft>(EMPTY_DRAFT);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const sessions = useMemo(
    () => [...(meetings ?? [])].sort((a, b) => a.meeting_index - b.meeting_index),
    [meetings]
  );
  const hasSessions = sessions.length > 0;
  const nextIndex = useMemo(
    () => (sessions.reduce((max, m) => Math.max(max, m.meeting_index), 0) + 1).toString(),
    [sessions]
  );

  const setField = useCallback((field: keyof SessionDraft, value: string) => {
    setDraft((prev) => ({ ...prev, [field]: value }));
  }, []);

  const resetForm = useCallback(() => {
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setFormError(null);
  }, []);

  const startEdit = useCallback((meeting: Meeting) => {
    setEditingId(meeting.id);
    setFormError(null);
    setDraft({
      meetingIndex: meeting.meeting_index.toString(),
      scheduledAt: toLocalInput(meeting.scheduled_at),
      durationMinutes: meeting.duration_minutes.toString(),
      location: meeting.location ?? "",
      topicSummary: meeting.topic_summary ?? "",
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    setFormError(null);
    const index = Number.parseInt(draft.meetingIndex || nextIndex, 10);
    if (!Number.isFinite(index) || index < 1) {
      setFormError(t("form.indexRequired"));
      return;
    }
    if (!draft.scheduledAt) {
      setFormError(t("form.dateRequired"));
      return;
    }
    const scheduledAt = new Date(draft.scheduledAt);
    if (Number.isNaN(scheduledAt.getTime())) {
      setFormError(t("form.dateRequired"));
      return;
    }
    const duration = Number.parseInt(draft.durationMinutes, 10);
    const payload = {
      meeting_index: index,
      scheduled_at: scheduledAt.toISOString(),
      duration_minutes: Number.isFinite(duration) && duration > 0 ? duration : 60,
      location: draft.location.trim() || null,
      topic_summary: draft.topicSummary.trim() || null,
    };
    try {
      if (editingId) {
        await updateMeeting.mutateAsync({ meetingId: editingId, patch: payload });
      } else {
        await createMeeting.mutateAsync(payload);
      }
      resetForm();
    } catch {
      setFormError(t("form.saveError"));
    }
  }, [draft, editingId, nextIndex, createMeeting, updateMeeting, resetForm, t]);

  const handleDelete = useCallback(
    async (meetingId: string) => {
      setActionError(null);
      try {
        await deleteMeeting.mutateAsync(meetingId);
        if (editingId === meetingId) resetForm();
      } catch {
        setActionError(t("deleteError"));
      }
    },
    [deleteMeeting, editingId, resetForm, t]
  );

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "schedule", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const isSaving = createMeeting.isPending || updateMeeting.isPending;
  const isFlipping = setStep.isPending;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          noValidate
          className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
        >
          <p className="text-[13px] font-semibold text-[var(--color-text)]">
            {editingId ? t("form.editTitle") : t("form.addTitle")}
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="session-index">{t("form.index")}</Label>
              <Input
                id="session-index"
                type="number"
                min={1}
                inputMode="numeric"
                placeholder={nextIndex}
                value={draft.meetingIndex}
                onChange={(e) => setField("meetingIndex", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="session-duration">{t("form.duration")}</Label>
              <Input
                id="session-duration"
                type="number"
                min={1}
                inputMode="numeric"
                value={draft.durationMinutes}
                onChange={(e) => setField("durationMinutes", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="session-date">{t("form.date")}</Label>
              <Input
                id="session-date"
                type="datetime-local"
                value={draft.scheduledAt}
                onChange={(e) => setField("scheduledAt", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="session-venue">{t("form.venue")}</Label>
              <Input
                id="session-venue"
                placeholder={t("form.venuePlaceholder")}
                value={draft.location}
                onChange={(e) => setField("location", e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="session-topic">{t("form.topic")}</Label>
            <Textarea
              id="session-topic"
              rows={2}
              placeholder={t("form.topicPlaceholder")}
              value={draft.topicSummary}
              onChange={(e) => setField("topicSummary", e.target.value)}
            />
          </div>

          {formError ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {formError}
            </p>
          ) : null}

          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={isSaving}>
              {isSaving ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
              {editingId ? t("form.saveEdit") : t("form.add")}
            </Button>
            {editingId ? (
              <Button type="button" size="sm" variant="ghost" onClick={resetForm}>
                {t("form.cancel")}
              </Button>
            ) : null}
          </div>
        </form>

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={!hasSessions || isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
            {t("continue")}
          </Button>
        </div>
      </div>

      <SessionsAside
        sessions={sessions}
        isLoading={isLoading}
        editingId={editingId}
        onEdit={startEdit}
        onDelete={handleDelete}
        onToggleRelease={setActionError}
        courseId={courseId}
        t={t}
      />
    </div>
  );
}

interface SessionsAsideProps {
  readonly sessions: readonly Meeting[];
  readonly isLoading: boolean;
  readonly editingId: string | null;
  readonly onEdit: (meeting: Meeting) => void;
  readonly onDelete: (meetingId: string) => void;
  readonly onToggleRelease: (error: string | null) => void;
  readonly courseId: string;
  readonly t: ReturnType<typeof useTranslations>;
}

function SessionsAside({
  sessions,
  isLoading,
  editingId,
  onEdit,
  onDelete,
  onToggleRelease,
  courseId,
  t,
}: SessionsAsideProps) {
  const setReleaseState = useSetMeetingReleaseState(courseId);

  const toggleRelease = useCallback(
    async (meeting: Meeting) => {
      onToggleRelease(null);
      const target = meeting.release_state === "locked" ? "released" : "locked";
      // Only locked<->released is reversible; other states are managed later.
      if (meeting.release_state !== "locked" && meeting.release_state !== "released") {
        return;
      }
      try {
        await setReleaseState.mutateAsync({ meetingId: meeting.id, releaseState: target });
      } catch {
        onToggleRelease(t("releaseError"));
      }
    },
    [setReleaseState, onToggleRelease, t]
  );

  return (
    <aside
      aria-label={t("sessionsLabel")}
      className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
    >
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("sessionsTitle")}
      </p>

      <div className="mt-4">
        {isLoading ? (
          <EmptyState variant="waiting" title={t("loading")} />
        ) : sessions.length === 0 ? (
          <EmptyState
            variant="empty"
            icon={CalendarClock}
            title={t("empty.title")}
            reason={t("empty.reason")}
          />
        ) : (
          <ul className="space-y-2.5">
            {sessions.map((meeting) => {
              const released = meeting.release_state === "released";
              return (
                <li
                  key={meeting.id}
                  className={
                    "space-y-1.5 rounded-[var(--radius-md)] border p-3 " +
                    (editingId === meeting.id
                      ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                      : "border-[var(--color-border)] bg-[var(--color-surface-hover)]")
                  }
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-[13px] font-semibold text-[var(--color-text)]">
                      {t("sessionLabel", { index: meeting.meeting_index })}
                    </p>
                    <div className="flex shrink-0 items-center gap-0.5">
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        aria-label={released ? t("lock") : t("release")}
                        disabled={setReleaseState.isPending}
                        onClick={() => void toggleRelease(meeting)}
                      >
                        {released ? (
                          <Eye aria-hidden="true" className="text-[var(--color-success)]" />
                        ) : (
                          <EyeOff aria-hidden="true" />
                        )}
                      </Button>
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        aria-label={t("editSession")}
                        onClick={() => onEdit(meeting)}
                      >
                        <Pencil aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        size="icon-xs"
                        variant="ghost"
                        aria-label={t("deleteSession")}
                        onClick={() => onDelete(meeting.id)}
                      >
                        <Trash2 aria-hidden="true" className="text-[var(--color-error)]" />
                      </Button>
                    </div>
                  </div>
                  <p className="flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)]">
                    <CalendarClock aria-hidden="true" className="size-3.5 shrink-0" />
                    {formatWhen(meeting.scheduled_at)}
                  </p>
                  {meeting.location ? (
                    <p className="flex items-center gap-1.5 text-[12px] text-[var(--color-text-secondary)]">
                      <MapPin aria-hidden="true" className="size-3.5 shrink-0" />
                      {meeting.location}
                    </p>
                  ) : null}
                  {meeting.topic_summary ? (
                    <p className="line-clamp-2 text-[12px] leading-relaxed text-[var(--color-text-muted)]">
                      {meeting.topic_summary}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <p className="mt-4 flex gap-2 text-[12px] leading-relaxed text-[var(--color-text-muted)]">
        <Sparkles aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.85} />
        {t("sessionsNote")}
      </p>
    </aside>
  );
}
