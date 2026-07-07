"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { ArrowLeft, Check, CircleDashed, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError } from "@/lib/api";
import {
  useMeetings,
  useUpdateMeeting,
  useSetMeetingReleaseState,
  type Meeting,
  type MeetingUpdate,
  type ReleaseState,
} from "@/hooks/use-meetings";
import {
  useCheckpoints,
  useCheckpointHistory,
  type Checkpoint,
} from "@/hooks/use-checkpoints";

import { StatusChip, releaseTone } from "./session-status";

const RELEASE_STATES: readonly ReleaseState[] = [
  "locked",
  "released",
  "completed",
  "archived",
];

interface SessionEditFormProps {
  readonly courseId: string;
  readonly meetingId: string;
}

interface FormState {
  readonly date: string;
  readonly time: string;
  readonly location: string;
  readonly duration: string;
  readonly topic: string;
  readonly releaseState: ReleaseState;
}

const pad = (n: number): string => String(n).padStart(2, "0");

/** Split a stored ISO instant into local `YYYY-MM-DD` + `HH:mm` for the inputs. */
function toLocalParts(iso: string): { readonly date: string; readonly time: string } {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { date: "", time: "" };
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  };
}

function seedForm(meeting: Meeting): FormState {
  const { date, time } = toLocalParts(meeting.scheduled_at);
  return {
    date,
    time,
    location: meeting.location ?? "",
    duration: String(meeting.duration_minutes),
    topic: meeting.topic_summary ?? "",
    releaseState: meeting.release_state,
  };
}

/**
 * T039 — teacher session edit + release-state control. Edits the session fields
 * (date/time, venue, duration, topic) via `useUpdateMeeting` and the
 * student-visibility axis via the P1 `useSetMeetingReleaseState` release-state
 * PATCH — the two are separate backend endpoints, so a save fans out to whichever
 * changed. Illegal release transitions come back as a typed
 * `ILLEGAL_RELEASE_TRANSITION` 409, surfaced inline. A derived release checklist
 * shows what still blocks students from a useful session.
 */
export function SessionEditForm({ courseId, meetingId }: SessionEditFormProps) {
  const t = useTranslations("teacher.sessions");
  const router = useRouter();
  const { data: meetingsData, isLoading } = useMeetings(courseId);
  const { data: draftCheckpoints } = useCheckpoints(courseId);
  const { data: historyCheckpoints } = useCheckpointHistory(courseId);

  const updateMeeting = useUpdateMeeting(courseId);
  const setReleaseState = useSetMeetingReleaseState(courseId);

  const meeting = meetingsData?.find((m) => m.id === meetingId);
  const detailHref = `/teacher/courses/${courseId}/sessions/${meetingId}`;
  const listHref = `/teacher/courses/${courseId}/sessions`;

  const [form, setForm] = useState<FormState | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Seed the controlled form once the meeting resolves (idempotent).
  const current = form ?? (meeting ? seedForm(meeting) : null);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void => {
    setForm((prev) => {
      const base = prev ?? (meeting ? seedForm(meeting) : null);
      if (!base) return prev;
      return { ...base, [key]: value };
    });
  };

  const checkpoints: readonly Checkpoint[] = [
    ...(draftCheckpoints ?? []),
    ...(historyCheckpoints ?? []),
  ].filter((cp) => cp.meeting_id === meetingId);

  const submitting = updateMeeting.isPending || setReleaseState.isPending;

  const onSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    if (!meeting || !current) return;
    setError(null);

    // Recombine local date + time into a stored ISO instant.
    const scheduledAt =
      current.date && current.time
        ? new Date(`${current.date}T${current.time}`).toISOString()
        : meeting.scheduled_at;
    const duration = Number.parseInt(current.duration, 10);

    const patch: MeetingUpdate = {
      scheduled_at: scheduledAt,
      location: current.location.trim() || null,
      duration_minutes: Number.isFinite(duration)
        ? duration
        : meeting.duration_minutes,
      topic_summary: current.topic.trim() || null,
    };
    const releaseChanged = current.releaseState !== meeting.release_state;

    try {
      await updateMeeting.mutateAsync({ meetingId, patch });
      if (releaseChanged) {
        await setReleaseState.mutateAsync({
          meetingId,
          releaseState: current.releaseState,
        });
      }
      router.push(detailHref);
    } catch (err) {
      if (err instanceof ApiError && err.code === "ILLEGAL_RELEASE_TRANSITION") {
        setError(t("edit.illegalTransition"));
      } else {
        setError(t("edit.saveError"));
      }
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-72 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (!meeting || !current) {
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

  return (
    <div className="space-y-6">
      <Link
        href={detailHref}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        {t("edit.back")}
      </Link>

      <div className="space-y-1">
        <h2 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("edit.title", { index: meeting.meeting_index })}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("edit.subtitle")}
        </p>
      </div>

      <form
        onSubmit={(e) => void onSubmit(e)}
        className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start"
      >
        <div className="space-y-5 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="grid gap-5 sm:grid-cols-2">
            <Field id="session-date" label={t("edit.date")}>
              <Input
                id="session-date"
                type="date"
                value={current.date}
                onChange={(e) => set("date", e.target.value)}
              />
            </Field>
            <Field id="session-time" label={t("edit.time")}>
              <Input
                id="session-time"
                type="time"
                value={current.time}
                onChange={(e) => set("time", e.target.value)}
              />
            </Field>
            <Field id="session-venue" label={t("edit.venue")}>
              <Input
                id="session-venue"
                value={current.location}
                placeholder={t("edit.venuePlaceholder")}
                onChange={(e) => set("location", e.target.value)}
              />
            </Field>
            <Field id="session-duration" label={t("edit.duration")}>
              <Input
                id="session-duration"
                type="number"
                min={1}
                value={current.duration}
                onChange={(e) => set("duration", e.target.value)}
              />
            </Field>
          </div>

          <Field id="session-release" label={t("edit.releaseState")}>
            <Select
              value={current.releaseState}
              onValueChange={(val) =>
                set("releaseState", (val ?? current.releaseState) as ReleaseState)
              }
            >
              <SelectTrigger id="session-release" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RELEASE_STATES.map((state) => (
                  <SelectItem key={state} value={state}>
                    {t(`release.${state}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[12px] text-[var(--color-text-muted)]">
              {t(`edit.releaseHint.${current.releaseState}`)}
            </p>
          </Field>

          <Field id="session-topic" label={t("edit.topic")}>
            <Textarea
              id="session-topic"
              rows={2}
              value={current.topic}
              placeholder={t("edit.topicPlaceholder")}
              onChange={(e) => set("topic", e.target.value)}
            />
          </Field>

          {error ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {error}
            </p>
          ) : null}

          <StateBanner
            tone="info"
            title={t("edit.visibilityNoticeTitle")}
            reason={t("edit.visibilityNoticeReason")}
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={submitting}>
              {submitting ? (
                <Loader2 aria-hidden="true" className="animate-spin" />
              ) : (
                <Check aria-hidden="true" />
              )}
              {t("edit.save")}
            </Button>
            <Button
              type="button"
              variant="ghost"
              render={<Link href={detailHref} />}
            >
              {t("edit.cancel")}
            </Button>
          </div>
        </div>

        <ReleaseChecklist
          meeting={meeting}
          pendingState={current.releaseState}
          checkpoints={checkpoints}
        />
      </form>
    </div>
  );
}

interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly children: React.ReactNode;
}

function Field({ id, label, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

interface ReleaseChecklistProps {
  readonly meeting: Meeting;
  readonly pendingState: ReleaseState;
  readonly checkpoints: readonly Checkpoint[];
}

/**
 * Derived readiness panel: is a checkpoint staged, is the session visible to
 * students, and is a calendar event linked. Purely informational — it reads the
 * pending release selection so the "visible" row reflects the unsaved choice.
 */
function ReleaseChecklist({
  meeting,
  pendingState,
  checkpoints,
}: ReleaseChecklistProps) {
  const t = useTranslations("teacher.sessions.edit.checklist");
  const checkpointReady = checkpoints.some((cp) =>
    ["approved", "scheduled", "published", "live"].includes(cp.status)
  );
  const items = [
    { key: "checkpoint", done: checkpointReady },
    { key: "visible", done: pendingState === "released" },
    { key: "calendar", done: Boolean(meeting.canvas_event_id) },
  ] as const;

  return (
    <aside className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("title")}
        </p>
        <StatusChip
          tone={releaseTone(pendingState)}
          label={t(`state.${pendingState}`)}
        />
      </div>
      <ul className="space-y-3">
        {items.map(({ key, done }) => (
          <li key={key} className="flex items-start gap-2.5">
            {done ? (
              <Check
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-[var(--color-success)]"
              />
            ) : (
              <CircleDashed
                aria-hidden="true"
                className="mt-0.5 size-4 shrink-0 text-[var(--color-text-muted)]"
              />
            )}
            <div className="min-w-0 space-y-0.5">
              <p className="text-[13px] font-medium text-[var(--color-text)]">
                {t(`items.${key}.title`)}
              </p>
              <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
                {t(`items.${key}.${done ? "done" : "todo"}`)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
