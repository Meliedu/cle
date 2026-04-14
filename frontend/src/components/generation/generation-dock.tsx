"use client";

import { useMemo, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  Layers,
  Loader2,
  X,
} from "lucide-react";
import {
  useGenerationJobs,
  type GenerationJob,
  type GenerationJobKind,
} from "@/hooks/use-generation-jobs";

const KIND_ICON: Record<GenerationJobKind, typeof BookOpen> = {
  generate_quiz: BookOpen,
  generate_flashcards: Layers,
  generate_summary: FileText,
};

const KIND_LABEL: Record<GenerationJobKind, string> = {
  generate_quiz: "Quiz",
  generate_flashcards: "Flashcards",
  generate_summary: "Summary",
};

function isActive(j: GenerationJob): boolean {
  return j.status === "pending" || j.status === "running";
}

export function GenerationDock() {
  const { jobs, dismissJob, dismissAllFinished } = useGenerationJobs();
  const [collapsed, setCollapsed] = useState(false);

  const { activeCount, completedCount, total } = useMemo(() => {
    let active = 0;
    let completed = 0;
    for (const j of jobs) {
      if (isActive(j)) active++;
      else if (j.status === "completed") completed++;
    }
    return { activeCount: active, completedCount: completed, total: jobs.length };
  }, [jobs]);

  if (total === 0) return null;

  const headerText =
    activeCount > 0
      ? `Generating ${activeCount} ${activeCount === 1 ? "item" : "items"}`
      : completedCount === total
        ? `${completedCount} ${completedCount === 1 ? "item" : "items"} ready`
        : `${completedCount} of ${total} ready`;

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-auto fixed bottom-4 right-4 z-50 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-[var(--radius-lg,0.75rem)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl"
    >
      <header className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-bg,rgba(0,0,0,0.02))] px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {activeCount > 0 ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-[var(--color-primary)]" />
          ) : (
            <Check className="size-4 shrink-0 text-[var(--color-success,#2a9d8f)]" />
          )}
          <p className="truncate text-sm font-medium text-[var(--color-text)]">
            {headerText}
          </p>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            aria-label={collapsed ? "Expand" : "Collapse"}
            onClick={() => setCollapsed((v) => !v)}
            className="rounded-md p-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover,rgba(0,0,0,0.04))] hover:text-[var(--color-text)]"
          >
            <ChevronDown
              className={`size-4 transition-transform ${
                collapsed ? "rotate-180" : ""
              }`}
            />
          </button>
          <button
            type="button"
            aria-label="Close"
            onClick={() => dismissAllFinished()}
            disabled={activeCount > 0 && completedCount === 0}
            title={
              activeCount > 0 && completedCount === 0
                ? "Can't close while jobs are still running"
                : "Clear completed"
            }
            className="rounded-md p-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover,rgba(0,0,0,0.04))] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-40"
          >
            <X className="size-4" />
          </button>
        </div>
      </header>

      {!collapsed && (
        <ul className="max-h-[min(60vh,24rem)] divide-y divide-[var(--color-border)] overflow-y-auto">
          {jobs.map((job) => (
            <DockRow key={job.jobId} job={job} onDismiss={dismissJob} />
          ))}
        </ul>
      )}
    </div>
  );
}

function DockRow({
  job,
  onDismiss,
}: {
  readonly job: GenerationJob;
  readonly onDismiss: (jobId: string) => void;
}) {
  const Icon = KIND_ICON[job.kind];
  const label = KIND_LABEL[job.kind];
  const displayTitle = job.title ?? label;

  const statusNode = (() => {
    if (isActive(job)) {
      return (
        <Loader2 className="size-4 animate-spin text-[var(--color-primary)]" />
      );
    }
    if (job.status === "completed") {
      return <Check className="size-4 text-[var(--color-success,#2a9d8f)]" />;
    }
    return <X className="size-4 text-[var(--color-error,#c00)]" />;
  })();

  const href = openHrefFor(job);

  const body = (
    <div className="flex flex-1 items-center gap-3 px-3 py-2.5">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-[var(--color-primary-light,#f5e9d5)]">
        <Icon className="size-4 text-[var(--color-primary)]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[var(--color-text)]">
          {displayTitle}
        </p>
        <p className="truncate text-xs text-[var(--color-text-muted)]">
          {rowSubtitle(job, label)}
        </p>
        {isActive(job) && <IndeterminateBar />}
      </div>
      <div className="shrink-0">{statusNode}</div>
    </div>
  );

  return (
    <li className="flex items-stretch">
      {href && !isActive(job) ? (
        <a
          href={href}
          className="flex flex-1 transition-colors hover:bg-[var(--color-surface-hover,rgba(0,0,0,0.04))]"
        >
          {body}
        </a>
      ) : (
        body
      )}
      {!isActive(job) && (
        <button
          type="button"
          aria-label="Dismiss"
          onClick={() => onDismiss(job.jobId)}
          className="shrink-0 px-2 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover,rgba(0,0,0,0.04))] hover:text-[var(--color-text)]"
        >
          <X className="size-3.5" />
        </button>
      )}
    </li>
  );
}

function IndeterminateBar() {
  return (
    <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
      <div className="h-full w-1/3 animate-[generation-dock-progress_1.4s_ease-in-out_infinite] rounded-full bg-[var(--color-primary)]" />
      <style jsx>{`
        @keyframes generation-dock-progress {
          0% {
            margin-left: -33%;
          }
          100% {
            margin-left: 100%;
          }
        }
      `}</style>
    </div>
  );
}

function rowSubtitle(job: GenerationJob, kindLabel: string): string {
  if (job.status === "pending") return `${kindLabel} · Queued`;
  if (job.status === "running") return `${kindLabel} · Generating…`;
  if (job.status === "completed") {
    if (job.kind === "generate_quiz" && job.result?.question_count != null) {
      return `${kindLabel} · ${job.result.question_count} questions`;
    }
    if (job.kind === "generate_flashcards" && job.result?.card_count != null) {
      return `${kindLabel} · ${job.result.card_count} cards`;
    }
    return `${kindLabel} · Ready`;
  }
  return `${kindLabel} · ${job.error ?? "Failed"}`;
}

function openHrefFor(job: GenerationJob): string | null {
  if (!job.result) return null;
  if (job.kind === "generate_quiz" && job.result.quiz_id) {
    return `/dashboard/courses/${job.courseId}/quizzes/${job.result.quiz_id}`;
  }
  if (job.kind === "generate_flashcards" && job.result.flashcard_set_id) {
    return `/dashboard/courses/${job.courseId}/flashcards/${job.result.flashcard_set_id}`;
  }
  if (job.kind === "generate_summary") {
    return `/dashboard/courses/${job.courseId}`;
  }
  return null;
}
