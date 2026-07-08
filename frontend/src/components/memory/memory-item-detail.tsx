"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  Clock,
  Link2,
  MessageSquareText,
  TrendingUp,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import type { MemoryItemResponse } from "@/hooks/use-memory";

import { MemoryDecideControls } from "./memory-decide-controls";
import {
  DECISION_ICON,
  decisionBadgeClass,
  decisionSlot,
  historyEntry,
  summaryText,
} from "./memory-format";

interface MemoryItemDetailProps {
  readonly courseId: string;
  readonly item: MemoryItemResponse;
  /** Optional back affordance (shown on narrow viewports for the two-pane list). */
  readonly onBack?: () => void;
}

/**
 * T087 — course memory item detail. Renders the reviewed relationship / action
 * / outcome summaries + the instructor comment, the audited decide controls,
 * and a history timeline over `report_history`. Free-form summary JSONBs are
 * flattened to human text via `summaryText`; a genuinely empty summary shows a
 * muted fallback rather than a blank block.
 */
export function MemoryItemDetail({
  courseId,
  item,
  onBack,
}: MemoryItemDetailProps) {
  const t = useTranslations("teacher.memory.detail");
  const tDecision = useTranslations("teacher.memory.decision");
  const slot = decisionSlot(item.decision);
  const DecisionIcon = DECISION_ICON[slot];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
              decisionBadgeClass(slot)
            )}
          >
            <DecisionIcon aria-hidden="true" className="size-3" />
            {tDecision(slot)}
          </span>
          <span className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-muted)]">
            <Clock aria-hidden="true" className="size-3.5" />
            {t("created", { time: formatRelativeTime(item.created_at) })}
          </span>
        </div>
        {onBack ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="lg:hidden"
            onClick={onBack}
          >
            <ArrowLeft aria-hidden="true" className="size-3.5" />
            {t("back")}
          </Button>
        ) : null}
      </div>

      {item.learning_note_id ? (
        <p className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-text-muted)]">
          <Link2 aria-hidden="true" className="size-3.5" />
          {t("noteLinked")}
        </p>
      ) : null}

      <div className="space-y-3">
        <SummaryBlock
          icon={Users}
          label={t("relationship")}
          text={summaryText(item.relationship_summary)}
          fallback={t("noSummary")}
        />
        <SummaryBlock
          icon={Wrench}
          label={t("action")}
          text={summaryText(item.action_summary)}
          fallback={t("noSummary")}
        />
        <SummaryBlock
          icon={TrendingUp}
          label={t("outcome")}
          text={summaryText(item.outcome_summary)}
          fallback={t("noSummary")}
        />
        {item.instructor_comment ? (
          <SummaryBlock
            icon={MessageSquareText}
            label={t("instructorComment")}
            text={item.instructor_comment}
            fallback={t("noSummary")}
            tone="accent"
          />
        ) : null}
      </div>

      <MemoryDecideControls courseId={courseId} item={item} />

      <HistoryTimeline history={item.report_history} />
    </div>
  );
}

interface SummaryBlockProps {
  readonly icon: LucideIcon;
  readonly label: string;
  readonly text: string | null;
  readonly fallback: string;
  readonly tone?: "default" | "accent";
}

function SummaryBlock({
  icon: Icon,
  label,
  text,
  fallback,
  tone = "default",
}: SummaryBlockProps) {
  const empty = text === null;
  return (
    <div
      className={cn(
        "rounded-[var(--radius-lg)] border p-4",
        tone === "accent"
          ? "border-[var(--color-accent)]/30 bg-[var(--color-accent-light)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)]"
      )}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <Icon
          aria-hidden="true"
          strokeWidth={1.85}
          className={cn(
            "size-3.5",
            tone === "accent"
              ? "text-[var(--color-accent)]"
              : "text-[var(--color-text-muted)]"
          )}
        />
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </span>
      </div>
      <p
        className={cn(
          "text-[13px] leading-relaxed",
          empty
            ? "italic text-[var(--color-text-muted)]"
            : "text-[var(--color-text)]"
        )}
      >
        {text ?? fallback}
      </p>
    </div>
  );
}

function HistoryTimeline({
  history,
}: {
  readonly history: readonly Record<string, unknown>[];
}) {
  const t = useTranslations("teacher.memory.detail");

  return (
    <section className="space-y-3">
      <h3 className="text-[13px] font-semibold text-[var(--color-text)]">
        {t("history")}
      </h3>
      {history.length === 0 ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("historyEmpty")}
        </p>
      ) : (
        <ol className="space-y-0">
          {history.map((raw, index) => {
            const entry = historyEntry(raw);
            const last = index === history.length - 1;
            return (
              <TimelineRow
                key={index}
                label={entry.label}
                at={
                  entry.at ? formatRelativeTime(entry.at) : null
                }
                last={last}
              />
            );
          })}
        </ol>
      )}
    </section>
  );
}

function TimelineRow({
  label,
  at,
  last,
}: {
  readonly label: string;
  readonly at: string | null;
  readonly last: boolean;
}): ReactNode {
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className="mt-1 size-2 shrink-0 rounded-full bg-[var(--color-primary)]" />
        {!last ? (
          <span className="w-px flex-1 bg-[var(--color-border)]" />
        ) : null}
      </div>
      <div className={cn("pb-4", last && "pb-0")}>
        <p className="text-[13px] font-medium text-[var(--color-text)]">
          {label}
        </p>
        {at ? (
          <p className="text-[11px] text-[var(--color-text-muted)]">{at}</p>
        ) : null}
      </div>
    </li>
  );
}
