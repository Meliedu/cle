import { cn } from "@/lib/utils";
import type { ReleaseState } from "@/hooks/use-meetings";
import type { Checkpoint, CheckpointStatus } from "@/hooks/use-checkpoints";

/**
 * One visual treatment per state-machine status, shared by the sessions list,
 * detail, and edit surfaces (T16). Each state maps to exactly one semantic
 * tone; the chip renders a soft token-backed pill so the same status always
 * reads the same across screens. Labels come from the caller (next-intl key),
 * keeping this component copy-free.
 */

export type StatusTone = "neutral" | "info" | "progress" | "success" | "muted";

const TONE_CLASS: Record<StatusTone, string> = {
  neutral:
    "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]",
  info: "border-transparent bg-[var(--color-accent-light)] text-[var(--color-accent-hover)]",
  progress:
    "border-transparent bg-[var(--color-warning-light)] text-[var(--color-warning)]",
  success:
    "border-transparent bg-[var(--color-success-light)] text-[var(--color-success)]",
  muted:
    "border-[var(--color-border)] bg-transparent text-[var(--color-text-muted)]",
};

interface StatusChipProps {
  readonly tone: StatusTone;
  readonly label: string;
  readonly className?: string;
}

/** Small pill with a single tone per status. */
export function StatusChip({ tone, label, className }: StatusChipProps) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center rounded-[var(--radius-pill)] border px-2 text-[11px] font-medium",
        TONE_CLASS[tone],
        className
      )}
    >
      {label}
    </span>
  );
}

/** Release-state → tone. Locked hides from students; completed/archived read as done. */
export function releaseTone(state: ReleaseState): StatusTone {
  switch (state) {
    case "released":
      return "success";
    case "completed":
      return "info";
    case "archived":
      return "muted";
    case "locked":
    default:
      return "neutral";
  }
}

/**
 * Checkpoint lifecycle → tone. Draft/teacher_editing are in-progress; approved
 * and scheduled are staged (info); published/live are success; closed/archived
 * read as done (muted).
 */
export function checkpointTone(status: CheckpointStatus): StatusTone {
  switch (status) {
    case "draft":
    case "teacher_editing":
      return "progress";
    case "approved":
    case "scheduled":
      return "info";
    case "published":
    case "live":
      return "success";
    case "closed":
    case "archived":
    default:
      return "muted";
  }
}

/**
 * Pick the checkpoint whose status best represents a session at a glance:
 * live/published beats scheduled/approved beats draft beats closed. Used by the
 * sessions list to show one chip per session even when several checkpoints
 * exist for a meeting.
 */
const STATUS_PRIORITY: readonly CheckpointStatus[] = [
  "live",
  "published",
  "scheduled",
  "approved",
  "teacher_editing",
  "draft",
  "closed",
  "archived",
];

export function primaryCheckpoint(
  checkpoints: readonly Checkpoint[]
): Checkpoint | null {
  if (checkpoints.length === 0) return null;
  return [...checkpoints].sort(
    (a, b) =>
      STATUS_PRIORITY.indexOf(a.status) - STATUS_PRIORITY.indexOf(b.status)
  )[0];
}

/** Group checkpoints by their `meeting_id` (null-keyed ones are dropped). */
export function groupByMeeting(
  checkpoints: readonly Checkpoint[]
): ReadonlyMap<string, readonly Checkpoint[]> {
  const map = new Map<string, Checkpoint[]>();
  for (const cp of checkpoints) {
    if (!cp.meeting_id) continue;
    const list = map.get(cp.meeting_id) ?? [];
    list.push(cp);
    map.set(cp.meeting_id, list);
  }
  return map;
}
