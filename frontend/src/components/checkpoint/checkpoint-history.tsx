"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { EmptyState, PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useMyCheckpointHistory,
  type StudentCheckpointHistoryItem,
} from "@/hooks/use-checkpoints";

import { HistoryStatusChip } from "./history-status-chip";

interface CheckpointHistoryProps {
  readonly courseId: string;
}

type HistoryFilter = "all" | "needs_revisit" | "completed";

/** Items whose derived status flags a gap the student may want to revisit. */
const NEEDS_REVISIT = new Set(["late", "missed"]);

function matchesFilter(
  item: StudentCheckpointHistoryItem,
  filter: HistoryFilter
): boolean {
  if (filter === "all") return true;
  if (filter === "completed") return item.derived_status === "complete";
  return NEEDS_REVISIT.has(item.derived_status);
}

/**
 * S039 — the student's checkpoint history for one course. A mobile-first list of
 * past checkpoints, each with its derived status chip (complete / late / missed
 * / upcoming) and a "Review" action that opens the follow-up. A small filter row
 * narrows to the items that need a revisit or those already complete.
 */
export function CheckpointHistory({ courseId }: CheckpointHistoryProps) {
  const t = useTranslations("student.checkpoint.history");
  const router = useRouter();
  const history = useMyCheckpointHistory(courseId);
  const [filter, setFilter] = useState<HistoryFilter>("all");

  const items = useMemo(
    () => (history.data ?? []).filter((item) => matchesFilter(item, filter)),
    [history.data, filter]
  );

  const filters: readonly HistoryFilter[] = ["all", "needs_revisit", "completed"];

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("subtitle")} />

      <div
        role="group"
        aria-label={t("filterLabel")}
        className="flex flex-wrap gap-2"
      >
        {filters.map((f) => {
          const active = filter === f;
          return (
            <button
              key={f}
              type="button"
              aria-pressed={active}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-[var(--radius-pill)] border px-3 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]",
                active
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
              )}
            >
              {t(`filter.${f}`)}
            </button>
          );
        })}
      </div>

      {history.isLoading ? (
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />
          <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />
        </div>
      ) : history.isError ? (
        <StateBanner
          tone="warning"
          title={t("loadErrorTitle")}
          reason={t("loadErrorReason")}
        />
      ) : items.length === 0 ? (
        <EmptyState title={t("emptyTitle")} reason={t("emptyReason")} />
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.checkpoint_id}>
              <HistoryRow
                item={item}
                onReview={() =>
                  router.push(
                    `/student/checkpoints/${item.checkpoint_id}/follow-up`
                  )
                }
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function HistoryRow({
  item,
  onReview,
}: {
  readonly item: StudentCheckpointHistoryItem;
  readonly onReview: () => void;
}) {
  const t = useTranslations("student.checkpoint.history");
  const showReview = NEEDS_REVISIT.has(item.derived_status);

  return (
    <div className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-[15px] font-semibold leading-snug tracking-tight text-[var(--color-text)]">
          {item.title}
        </h3>
        <HistoryStatusChip status={item.derived_status} />
      </div>

      <p className="text-[13px] text-[var(--color-text-secondary)]">
        {t("reviewPoints", {
          responded: item.responded_count,
          total: item.live_card_count,
        })}
      </p>

      {showReview ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onReview}
        >
          {t("review")}
        </Button>
      ) : null}
    </div>
  );
}
