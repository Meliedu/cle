import type { StateTone } from "@/components/patterns";

/**
 * Shared, pure formatting + tone helpers for the teacher-insights surface.
 * Kept side-effect-free so they are trivially unit-testable and reused across
 * the course-insights view, the signal drawer, the evidence-source view, and
 * the effectiveness tracker. No numbers are computed here — these only map
 * existing values to display strings / token classes.
 */

/** Alert / signal severity → the shared semantic tone. */
export function severityTone(severity: string): StateTone {
  switch (severity) {
    case "critical":
      return "blocked";
    case "warning":
      return "warning";
    default:
      return "info";
  }
}

/**
 * Outcome-check status → a badge treatment (text + soft background). `improved`
 * / `resolved` read as success; `persistent` / `needs_review` as warning;
 * everything else stays neutral.
 */
export function outcomeToneClass(status: string): string {
  switch (status) {
    case "improved":
    case "resolved":
      return "bg-[var(--color-success-light)] text-[var(--color-success)]";
    case "persistent":
    case "needs_review":
      return "bg-[var(--color-warning-light)] text-[var(--color-warning)]";
    case "carried_forward":
      return "bg-[var(--color-accent-light)] text-[var(--color-accent)]";
    default:
      return "bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]";
  }
}

/**
 * A `learning_note.review_status` → a compact chip treatment. Reviewed/published
 * states read confirmed; draft/queued read as pending review.
 */
export function reviewStatusToneClass(status: string): string {
  switch (status) {
    case "reviewed":
    case "edited":
    case "published":
      return "bg-[var(--color-success-light)] text-[var(--color-success)]";
    case "dismissed":
    case "archived":
      return "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]";
    default:
      // draft | queued | in_review — waiting on the instructor.
      return "bg-[var(--color-cream)] text-[var(--color-primary-hover)]";
  }
}

/** `true` while a note is still a draft the student must never see (Core §0.2). */
export function isPendingReview(status: string): boolean {
  return status === "draft" || status === "queued" || status === "in_review";
}

/**
 * Format a 0..1 mastery/strength fraction as a whole percent, or a dash when
 * there is no evidence (`null`) — never a fabricated `0%`.
 */
export function formatFraction(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

/** Clamp a 0..1 fraction to a CSS width percentage (0 when absent). */
export function barWidth(value: number | null | undefined): string {
  if (value === null || value === undefined) return "0%";
  return `${Math.min(100, Math.max(0, Math.round(value * 100)))}%`;
}
