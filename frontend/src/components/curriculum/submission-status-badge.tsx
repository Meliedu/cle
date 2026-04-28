import type { SubmissionStatus } from "@/lib/curriculum-types";

interface Props {
  readonly status: SubmissionStatus;
}

const STYLES: Record<SubmissionStatus, string> = {
  not_started: "bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]",
  in_progress: "bg-[var(--color-warning-light)] text-[var(--color-warning)] border border-[var(--color-warning)]",
  submitted:   "bg-[var(--color-accent-light)] text-[var(--color-accent)] border border-[var(--color-accent)]",
  late:        "bg-[var(--color-error-light)] text-[var(--color-error)] border border-[var(--color-error)]",
  graded:      "bg-[var(--color-success-light)] text-[var(--color-success)] border border-[var(--color-success)]",
  excused:     "bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]",
};

export function SubmissionStatusBadge({ status }: Props) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs ${STYLES[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
