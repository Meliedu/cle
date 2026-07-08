"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Brain } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useMemorySummary,
  type MemoryItemResponse,
} from "@/hooks/use-memory";

import {
  DECISION_ICON,
  DECISION_ORDER,
  decisionBadgeClass,
  summaryText,
  type DecisionSlot,
} from "./memory-format";

interface MemorySummaryProps {
  readonly courseId: string;
}

/**
 * T036 — course memory summary. A compact overview panel over
 * `useMemorySummary`: total reviewed items, a counts-by-decision strip, and the
 * carry-forward roster destined for next-term import. Mounted on the teacher
 * course overview. Stays quiet (returns nothing) for a course with no reviewed
 * memory yet so it never clutters a fresh course; a load error degrades to a
 * muted line rather than blocking the overview.
 */
export function MemorySummary({ courseId }: MemorySummaryProps) {
  const t = useTranslations("teacher.memory.summary");
  const tDecision = useTranslations("teacher.memory.decision");
  const { data, isLoading, isError } = useMemorySummary(courseId);

  if (isLoading) {
    return <Skeleton className="h-40 w-full rounded-[var(--radius-xl)]" />;
  }

  // A brand-new course has no reviewed memory — don't surface an empty panel.
  if (isError || !data || data.total === 0) {
    return null;
  }

  const memoryHref = `/teacher/courses/${courseId}/memory`;
  const roster = data.carry_forward_roster;

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
            <Brain aria-hidden="true" strokeWidth={1.85} className="size-5" />
          </span>
          <div className="space-y-0.5">
            <p className="text-[14px] font-semibold text-[var(--color-text)]">
              {t("title")}
            </p>
            <p className="text-[12px] text-[var(--color-text-muted)]">
              {t("total", { count: data.total })}
            </p>
          </div>
        </div>
        <Link
          href={memoryHref}
          className="inline-flex items-center gap-1 text-[13px] font-medium text-[var(--color-primary)] hover:underline"
        >
          {t("viewAll")}
          <ArrowRight aria-hidden="true" className="size-3.5" />
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        {DECISION_ORDER.map((slot) => (
          <CountChip
            key={slot}
            slot={slot}
            label={tDecision(slot)}
            count={data.counts[slot]}
          />
        ))}
      </div>

      <div className="space-y-2">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("rosterTitle")}
        </p>
        {roster.length === 0 ? (
          <p className="text-[13px] text-[var(--color-text-muted)]">
            {t("rosterEmpty")}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {roster.slice(0, 4).map((item) => (
              <RosterRow key={item.id} item={item} />
            ))}
            {roster.length > 4 ? (
              <li className="text-[12px] text-[var(--color-text-muted)]">
                {t("rosterMore", { count: roster.length - 4 })}
              </li>
            ) : null}
          </ul>
        )}
      </div>
    </section>
  );
}

function CountChip({
  slot,
  label,
  count,
}: {
  readonly slot: DecisionSlot;
  readonly label: string;
  readonly count: number;
}) {
  const Icon = DECISION_ICON[slot];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[12px] font-medium",
        count > 0
          ? decisionBadgeClass(slot)
          : "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]"
      )}
    >
      <Icon aria-hidden="true" className="size-3" />
      <span className="tabular-nums">{count}</span>
      {label}
    </span>
  );
}

function RosterRow({ item }: { readonly item: MemoryItemResponse }) {
  const text =
    summaryText(item.outcome_summary) ??
    summaryText(item.action_summary) ??
    summaryText(item.relationship_summary) ??
    item.instructor_comment;

  return (
    <li className="flex items-start gap-2">
      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-[var(--color-accent)]" />
      <p className="truncate text-[13px] text-[var(--color-text-secondary)]">
        {text ?? "—"}
      </p>
    </li>
  );
}
