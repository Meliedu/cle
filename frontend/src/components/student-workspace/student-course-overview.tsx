"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  FolderOpen,
  ListTodo,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { StatusChip } from "@/components/course/session-status";
import {
  useChecklist,
  useNextAction,
  type ChecklistItem,
} from "@/hooks/use-work-items";

import { SourceKindIcon } from "./source-kind";
import { isWorkItemDone, workItemTone } from "./work-item-status";

interface StudentCourseOverviewProps {
  readonly courseId: string;
}

/** Locale date + time, e.g. "Fri, 10 Jul · 23:59". */
function formatDue(iso: string): string {
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

interface Progress {
  readonly total: number;
  readonly done: number;
  readonly open: number;
  readonly missed: number;
  readonly percent: number;
}

function computeProgress(items: readonly ChecklistItem[]): Progress {
  const total = items.length;
  const done = items.filter((i) => isWorkItemDone(i.status)).length;
  const missed = items.filter((i) => i.status === "missed").length;
  const open = total - done - missed;
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return { total, done, open, missed, percent };
}

/**
 * S023 — student course overview. The workspace landing tab: the single
 * next-action drawn from the checklist spine (`useNextAction`) plus a progress
 * summary over the whole checklist (`useChecklist`) and quick links into the
 * other tabs. A clear checklist reads as a calm "all caught up" state; a course
 * with no work items yet gets a designed empty state, never a blank panel.
 */
export function StudentCourseOverview({
  courseId,
}: StudentCourseOverviewProps) {
  const t = useTranslations("student.workspace.overview");
  const checklist = useChecklist(courseId);
  const nextAction = useNextAction(courseId);

  const items = useMemo(() => checklist.data ?? [], [checklist.data]);
  const progress = useMemo(() => computeProgress(items), [items]);

  const base = `/student/courses/${courseId}`;

  if (checklist.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full rounded-[var(--radius-xl)]" />
        <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (checklist.isError) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  if (progress.total === 0) {
    return (
      <EmptyState
        icon={ListTodo}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  const next = nextAction.data ?? null;

  return (
    <div className="space-y-6">
      <NextActionCard courseId={courseId} next={next} />

      <ProgressCard progress={progress} />

      <div className="grid gap-3 sm:grid-cols-3">
        <QuickLink
          href={`${base}/schedule`}
          icon={CalendarDays}
          label={t("links.schedule")}
        />
        <QuickLink
          href={`${base}/sessions`}
          icon={FolderOpen}
          label={t("links.sessions")}
        />
        <QuickLink
          href={`${base}/materials`}
          icon={FolderOpen}
          label={t("links.materials")}
        />
      </div>
    </div>
  );
}

interface NextActionCardProps {
  readonly courseId: string;
  readonly next: ChecklistItem | null;
}

function NextActionCard({ courseId, next }: NextActionCardProps) {
  const t = useTranslations("student.workspace.overview");
  const tk = useTranslations("student.checklist.kind");

  if (!next) {
    return (
      <div className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] px-5 py-4">
        <CheckCircle2
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-5 shrink-0 text-[var(--color-success)]"
        />
        <div>
          <p className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("nextAction.clearTitle")}
          </p>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("nextAction.clearReason")}
          </p>
        </div>
      </div>
    );
  }

  const due = next.due_at ?? next.close_at;

  return (
    <div className="flex flex-col gap-4 rounded-[var(--radius-xl)] border border-[var(--color-primary)]/30 bg-[var(--color-primary-light)] p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[var(--color-primary)]">
          <SourceKindIcon kind={next.source_kind} className="size-5" />
        </div>
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-primary)]">
            {t("nextAction.label")}
          </p>
          <p className="truncate text-[15px] font-semibold text-[var(--color-text)]">
            {next.title}
          </p>
          <p className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--color-text-secondary)]">
            <StatusChip
              tone={workItemTone(next.status)}
              label={tk(next.source_kind)}
            />
            {due ? <span>{t("nextAction.due", { when: formatDue(due) })}</span> : null}
          </p>
        </div>
      </div>
      <Button
        size="sm"
        render={<Link href={`/student/courses/${courseId}/checklist`} />}
      >
        {t("nextAction.start")}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Button>
    </div>
  );
}

function ProgressCard({ progress }: { readonly progress: Progress }) {
  const t = useTranslations("student.workspace.overview");
  return (
    <div className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("progress.title")}
          </p>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("progress.summary", {
              done: progress.done,
              total: progress.total,
            })}
          </p>
        </div>
        <p className="text-[24px] font-bold leading-none text-[var(--color-primary)]">
          {progress.percent}%
        </p>
      </div>

      <div
        role="progressbar"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 w-full overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
      >
        <div
          className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)]"
          style={{ width: `${progress.percent}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12px]">
        <Stat label={t("progress.open")} value={progress.open} />
        <Stat label={t("progress.done")} value={progress.done} />
        {progress.missed > 0 ? (
          <Stat label={t("progress.missed")} value={progress.missed} />
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value }: { readonly label: string; readonly value: number }) {
  return (
    <span className="flex items-center gap-1.5 text-[var(--color-text-secondary)]">
      <span className="font-semibold text-[var(--color-text)]">{value}</span>
      {label}
    </span>
  );
}

interface QuickLinkProps {
  readonly href: string;
  readonly icon: LucideIcon;
  readonly label: string;
}

function QuickLink({ href, icon: Icon, label }: QuickLinkProps) {
  return (
    <Link
      href={href}
      className="flex items-center justify-between rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-[13px] font-medium text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]"
    >
      <span className="flex items-center gap-2.5">
        <Icon
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-4 text-[var(--color-text-muted)]"
        />
        {label}
      </span>
      <ArrowRight
        aria-hidden="true"
        className="size-4 text-[var(--color-text-muted)]"
      />
    </Link>
  );
}
