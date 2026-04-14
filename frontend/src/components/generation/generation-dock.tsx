"use client";

import { Loader2, X, BookOpen, Layers, FileText } from "lucide-react";
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

export function GenerationDock() {
  const { jobs, dismissJob } = useGenerationJobs();

  // Only in-flight jobs live in the dock. Completed/failed jobs are surfaced
  // via sonner toast and should be dismissed or auto-dismissed.
  const visible = jobs.filter(
    (j) => j.status === "pending" || j.status === "running"
  );

  if (visible.length === 0) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2"
    >
      {visible.map((job) => (
        <DockChip key={job.jobId} job={job} onDismiss={dismissJob} />
      ))}
    </div>
  );
}

function DockChip({
  job,
  onDismiss,
}: {
  readonly job: GenerationJob;
  readonly onDismiss: (jobId: string) => void;
}) {
  const Icon = KIND_ICON[job.kind];
  const label = KIND_LABEL[job.kind];
  const displayTitle = job.title ?? label;

  return (
    <div className="pointer-events-auto flex items-center gap-3 rounded-[var(--radius-lg,0.75rem)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 shadow-lg">
      <div className="relative flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light,#f5e9d5)]">
        <Loader2 className="absolute inset-0 m-auto size-9 animate-spin text-[var(--color-primary)]" />
        <Icon className="relative size-4 text-[var(--color-primary)]" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-[var(--color-text)]">
          Generating {label.toLowerCase()}
        </p>
        <p className="truncate text-xs text-[var(--color-text-muted)]">
          {displayTitle}
        </p>
      </div>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => onDismiss(job.jobId)}
        className="rounded-md p-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover,rgba(0,0,0,0.04))] hover:text-[var(--color-text)]"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
