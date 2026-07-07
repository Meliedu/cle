"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { HistoryDerivedStatus } from "@/hooks/use-checkpoints";

interface HistoryStatusChipProps {
  readonly status: HistoryDerivedStatus;
}

const STYLE: Record<
  HistoryDerivedStatus,
  { readonly icon: LucideIcon; readonly className: string }
> = {
  complete: {
    icon: CheckCircle2,
    className:
      "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]",
  },
  late: {
    icon: Clock,
    className:
      "border-[var(--color-warning)]/45 bg-[var(--color-warning-light)] text-[var(--color-warning)]",
  },
  missed: {
    icon: XCircle,
    className:
      "border-[var(--color-error)]/35 bg-[var(--color-error-light)] text-[var(--color-error)]",
  },
  upcoming: {
    icon: AlertTriangle,
    className:
      "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]",
  },
};

/**
 * Small status pill for a student's per-checkpoint derived status (S039):
 * complete / late / missed / upcoming. Colors follow the shared tone palette.
 */
export function HistoryStatusChip({ status }: HistoryStatusChipProps) {
  const t = useTranslations("student.checkpoint.history.status");
  const { icon: Icon, className } = STYLE[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] border px-2.5 py-1 text-[12px] font-medium",
        className
      )}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {t(status)}
    </span>
  );
}
