import {
  CheckCircle2,
  CircleCheck,
  PencilLine,
  Send,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ReportStatus } from "@/hooks/use-reports";

/**
 * One visual treatment per report `status` (spec §4.9 state machine:
 * draft → reviewed → sent → archived). A copy-free pill so the same status
 * always reads the same across the archive, detail, and action surfaces —
 * labels are supplied by the caller (next-intl key), mirroring the shared
 * `StatusChip` language in `course/session-status.tsx`. Color is never the sole
 * signal: each tone carries its own glyph (a11y `color-not-only`).
 */
export type ReportStatusTone = "draft" | "reviewed" | "sent" | "archived";

interface ToneTreatment {
  readonly Icon: LucideIcon;
  readonly className: string;
}

const TONE: Record<ReportStatusTone, ToneTreatment> = {
  // Draft — still editable, in-progress (warm honey).
  draft: {
    Icon: PencilLine,
    className:
      "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-hover)]",
  },
  // Reviewed — approved, staged to send (accent/info).
  reviewed: {
    Icon: CheckCircle2,
    className:
      "border-transparent bg-[var(--color-accent-light)] text-[var(--color-accent-hover)]",
  },
  // Sent — delivered to the student (success/done).
  sent: {
    Icon: Send,
    className:
      "border-transparent bg-[var(--color-success-light)] text-[var(--color-success)]",
  },
  // Archived — retired (muted).
  archived: {
    Icon: CircleCheck,
    className:
      "border-[var(--color-border)] bg-transparent text-[var(--color-text-muted)]",
  },
};

/** Every `ReportStatus` maps one-to-one onto a chip tone. */
export function reportStatusTone(status: ReportStatus): ReportStatusTone {
  return status;
}

interface ReportStatusChipProps {
  readonly status: ReportStatus;
  /** Localized status label (e.g. `t("status.draft")`). */
  readonly label: string;
  readonly className?: string;
}

/** Small tone-per-status pill with a glyph, for report rows and headers. */
export function ReportStatusChip({
  status,
  label,
  className,
}: ReportStatusChipProps) {
  const { Icon, className: tone } = TONE[reportStatusTone(status)];
  return (
    <span
      data-status={status}
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center gap-1 rounded-[var(--radius-pill)] border px-2 text-[11px] font-medium",
        tone,
        className
      )}
    >
      <Icon aria-hidden="true" strokeWidth={2} className="size-3" />
      {label}
    </span>
  );
}
