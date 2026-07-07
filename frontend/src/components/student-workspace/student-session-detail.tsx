"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  ClipboardCheck,
  Clock,
  FileText,
  Lock,
  MapPin,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import { StatusChip, releaseTone } from "@/components/course/session-status";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";
import {
  useMaterials,
  type DocumentResponse,
} from "@/hooks/use-documents";

interface StudentSessionDetailProps {
  readonly courseId: string;
  readonly meetingId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A locked/archived session is not yet open to students. */
function isLocked(meeting: Meeting): boolean {
  return (
    meeting.release_state === "locked" ||
    meeting.release_state === "archived"
  );
}

/**
 * S027 / S028 — student session detail. For a released (or completed) session
 * it shows the session facts, today's focus (`topic_summary`), and this
 * session's materials (grouped from `useMaterials`). A locked session renders
 * the designed "not open yet" state (S028) instead — the facts stay visible so
 * the student knows when it will open, but the content is withheld.
 */
export function StudentSessionDetail({
  courseId,
  meetingId,
}: StudentSessionDetailProps) {
  const t = useTranslations("student.sessions");
  const meetings = useMeetings(courseId);
  const materials = useMaterials(courseId);

  const meeting = useMemo(
    () => (meetings.data ?? []).find((m) => m.id === meetingId) ?? null,
    [meetings.data, meetingId]
  );

  const sessionDocs = useMemo<readonly DocumentResponse[]>(() => {
    const group = (materials.data?.sessions ?? []).find(
      (s) => s.meeting_id === meetingId
    );
    return group?.documents ?? [];
  }, [materials.data, meetingId]);

  const backHref = `/student/courses/${courseId}/sessions`;

  if (meetings.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="space-y-4">
        <BackLink href={backHref} label={t("backToList")} />
        <EmptyState
          icon={CalendarDays}
          title={t("notFound.title")}
          reason={t("notFound.reason")}
        />
      </div>
    );
  }

  const title = meeting.topic_summary || meeting.title || t("untitled");

  return (
    <div className="space-y-5">
      <BackLink href={backHref} label={t("backToList")} />

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("sessionLabel", { index: meeting.meeting_index })}
        </h2>
        <StatusChip
          tone={releaseTone(meeting.release_state)}
          label={t(`release.${meeting.release_state}`)}
        />
      </div>

      <SessionFacts meeting={meeting} />

      {isLocked(meeting) ? (
        <LockedCard />
      ) : (
        <>
          <FocusCard title={title} summary={meeting.topic_summary} />
          <MaterialsCard
            courseId={courseId}
            docs={sessionDocs}
            loading={materials.isLoading}
          />
          <CheckInCard courseId={courseId} />
        </>
      )}
    </div>
  );
}

function BackLink({ href, label }: { readonly href: string; readonly label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
    >
      <ArrowLeft aria-hidden="true" className="size-4" />
      {label}
    </Link>
  );
}

function SessionFacts({ meeting }: { readonly meeting: Meeting }) {
  const t = useTranslations("student.sessions");
  const facts = [
    { icon: CalendarDays, label: t("facts.date"), value: formatDate(meeting.scheduled_at) },
    { icon: Clock, label: t("facts.time"), value: formatTime(meeting.scheduled_at) },
    {
      icon: MapPin,
      label: t("facts.venue"),
      value: meeting.location || t("facts.venueTba"),
    },
  ] as const;

  return (
    <dl className="grid gap-3 sm:grid-cols-3">
      {facts.map(({ icon: Icon, label, value }) => (
        <div
          key={label}
          className="flex items-start gap-2.5 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
        >
          <Icon
            aria-hidden="true"
            strokeWidth={1.85}
            className="mt-0.5 size-4 shrink-0 text-[var(--color-text-muted)]"
          />
          <div className="min-w-0">
            <dt className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
              {label}
            </dt>
            <dd className="truncate text-[13px] font-medium text-[var(--color-text)]">
              {value}
            </dd>
          </div>
        </div>
      ))}
    </dl>
  );
}

function LockedCard() {
  const t = useTranslations("student.sessions.locked");
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-6 py-12 text-center">
      <div className="flex size-14 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-surface)]">
        <Lock
          aria-hidden="true"
          strokeWidth={1.75}
          className="size-6 text-[var(--color-text-muted)]"
        />
      </div>
      <div className="space-y-1.5">
        <h3 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h3>
        <p className="mx-auto max-w-[42ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("reason")}
        </p>
      </div>
    </div>
  );
}

function FocusCard({
  title,
  summary,
}: {
  readonly title: string;
  readonly summary: string | null;
}) {
  const t = useTranslations("student.sessions");
  return (
    <div className="space-y-2 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("focus")}
      </p>
      <p className="text-[15px] font-semibold text-[var(--color-text)]">
        {title}
      </p>
      {summary && summary !== title ? (
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {summary}
        </p>
      ) : null}
    </div>
  );
}

interface MaterialsCardProps {
  readonly courseId: string;
  readonly docs: readonly DocumentResponse[];
  readonly loading: boolean;
}

function MaterialsCard({ courseId, docs, loading }: MaterialsCardProps) {
  const t = useTranslations("student.sessions");
  const materialsHref = `/student/courses/${courseId}/materials`;

  return (
    <div className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("materials.title")}
      </p>
      {loading ? (
        <Skeleton className="h-10 w-full rounded-[var(--radius-md)]" />
      ) : docs.length === 0 ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("materials.empty")}
        </p>
      ) : (
        <ul className="space-y-1.5">
          {docs.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center gap-2.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-2"
            >
              <FileText
                aria-hidden="true"
                strokeWidth={1.85}
                className="size-4 shrink-0 text-[var(--color-text-muted)]"
              />
              <span className="min-w-0 flex-1 truncate text-[13px] text-[var(--color-text)]">
                {doc.filename}
              </span>
              <Link
                href={materialsHref}
                className="shrink-0 text-[12px] font-medium text-[var(--color-primary)] hover:underline"
              >
                {t("materials.open")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CheckInCard({ courseId }: { readonly courseId: string }) {
  const t = useTranslations("student.sessions.checkIn");
  const historyHref = `/student/courses/${courseId}/checkpoints`;
  return (
    <div className="flex items-start gap-3 rounded-[var(--radius-xl)] border border-[var(--color-accent)]/40 bg-[var(--color-accent-light)] p-5">
      <ClipboardCheck
        aria-hidden="true"
        strokeWidth={1.85}
        className="mt-0.5 size-5 shrink-0 text-[var(--color-accent)]"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[14px] font-semibold text-[var(--color-text)]">
          {t("title")}
        </p>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("reason")}
        </p>
      </div>
      <Button
        size="sm"
        variant="outline"
        render={<Link href={historyHref} />}
        className="shrink-0"
      >
        {t("view")}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Button>
    </div>
  );
}
