"use client";

import { useTranslations } from "next-intl";
import { Repeat2, TrendingUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import {
  useEffectiveness,
  type OutcomeStatusCounts,
} from "@/hooks/use-insights";

import { InsightCard } from "./insights-primitives";

/**
 * T079 — follow-up effectiveness tracker. RESHAPES `useEffectiveness` (the read
 * side of the evidence loop `_close_follow_ups` writes) into an
 * improved-vs-persistent breakdown of `outcome_checks`, both overall and per
 * follow-up `action_type`. Pure read — no new job, no recomputation. A course
 * with no tracked outcomes (`has_evidence === false`) renders the designed
 * no-evidence state rather than a wall of zeros.
 */

interface EffectivenessTrackerProps {
  readonly courseId: string;
}

/** The four outcome buckets that tell the improved-vs-persistent story. */
const STATUS_KEYS = [
  { key: "improved", tone: "success" },
  { key: "resolved", tone: "success" },
  { key: "persistent", tone: "warning" },
  { key: "needs_review", tone: "warning" },
] as const;

export function EffectivenessTracker({ courseId }: EffectivenessTrackerProps) {
  const t = useTranslations("teacher.insights");
  const { data, isLoading, isError } = useEffectiveness(courseId);

  if (isLoading) {
    return <Skeleton className="h-40 w-full" />;
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("effectiveness.loadErrorTitle")}
        reason={t("effectiveness.loadErrorReason")}
      />
    );
  }

  if (!data.has_evidence || data.total === 0) {
    return (
      <InsightCard title={t("effectiveness.title")} icon={TrendingUp}>
        <EmptyState
          variant="waiting"
          title={t("effectiveness.emptyTitle")}
          reason={t("effectiveness.emptyReason")}
          className="py-10"
        />
      </InsightCard>
    );
  }

  return (
    <InsightCard
      title={t("effectiveness.title")}
      subtitle={t("effectiveness.subtitle")}
      icon={TrendingUp}
    >
      <p className="text-[12px] text-[var(--color-text-muted)]">
        {t("effectiveness.total", { count: data.total })}
      </p>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {STATUS_KEYS.map(({ key, tone }) => (
          <OutcomeStat
            key={key}
            label={t(`effectiveness.${camel(key)}`)}
            count={data.by_status[key]}
            total={data.total}
            tone={tone}
          />
        ))}
      </div>

      {data.by_action_type.length > 0 ? (
        <div className="space-y-2.5 pt-1">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-[var(--color-text)]">
            <Repeat2 aria-hidden="true" strokeWidth={1.85} className="size-3.5" />
            {t("effectiveness.byType")}
          </p>
          <ul className="space-y-2">
            {data.by_action_type.map((row) => (
              <li key={row.action_type}>
                <ActionTypeRow
                  label={
                    t.has(`actionType.${row.action_type}`)
                      ? t(`actionType.${row.action_type}`)
                      : row.action_type
                  }
                  total={row.total}
                  byStatus={row.by_status}
                  totalLabel={t("effectiveness.typeTotal", { count: row.total })}
                />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </InsightCard>
  );
}

interface OutcomeStatProps {
  readonly label: string;
  readonly count: number;
  readonly total: number;
  readonly tone: "success" | "warning";
}

function OutcomeStat({ label, count, total, tone }: OutcomeStatProps) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  const fill =
    tone === "success" ? "bg-[var(--color-success)]" : "bg-[var(--color-warning)]";
  const valueColor =
    tone === "success"
      ? "text-[var(--color-success)]"
      : "text-[var(--color-warning)]";
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)]/70 bg-[var(--color-surface-hover)] p-3.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[12px] text-[var(--color-text-secondary)]">
          {label}
        </span>
        <span className={cn("text-[18px] font-bold leading-none", valueColor)}>
          {count}
        </span>
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface)]">
        <div className={cn("h-full rounded-full", fill)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface ActionTypeRowProps {
  readonly label: string;
  readonly total: number;
  readonly byStatus: OutcomeStatusCounts;
  readonly totalLabel: string;
}

function ActionTypeRow({ label, total, byStatus, totalLabel }: ActionTypeRowProps) {
  const improved = byStatus.improved + byStatus.resolved;
  const persistent = byStatus.persistent + byStatus.needs_review;
  const improvedPct = total > 0 ? (improved / total) * 100 : 0;
  const persistentPct = total > 0 ? (persistent / total) * 100 : 0;
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="truncate text-[13px] font-medium text-[var(--color-text)]">
          {label}
        </span>
        <span className="shrink-0 text-[11px] text-[var(--color-text-muted)]">
          {totalLabel}
        </span>
      </div>
      <div className="mt-2 flex h-2 w-full overflow-hidden rounded-full bg-[var(--color-surface-hover)]">
        <div
          className="h-full bg-[var(--color-success)]"
          style={{ width: `${improvedPct}%` }}
          aria-hidden="true"
        />
        <div
          className="h-full bg-[var(--color-warning)]"
          style={{ width: `${persistentPct}%` }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

/** Map a snake_case status key to its camelCase i18n leaf. */
function camel(key: string): string {
  return key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());
}
