"use client";

import { useTranslations } from "next-intl";
import { MessageSquareText } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/patterns";
import {
  useCheckpointResults,
  type CheckpointCardResult,
} from "@/hooks/use-checkpoints";

interface CheckpointResultsViewProps {
  readonly checkpointId: string;
}

const CONFIDENCE_KEYS = ["-2", "-1", "0", "1", "2"] as const;

/**
 * T048 — closed checkpoint results. The teacher's after-the-fact read of a
 * closed checkpoint: how many active students responded vs missed it, then a
 * per-card breakdown — a −2..+2 confidence distribution for each review point
 * and a response tally for the final-comments card. Read-only; the numbers are
 * final once the checkpoint has closed.
 */
export function CheckpointResultsView({ checkpointId }: CheckpointResultsViewProps) {
  const t = useTranslations("teacher.results");
  const { data, isLoading } = useCheckpointResults(checkpointId);

  if (isLoading) {
    return <Skeleton className="h-48 w-full rounded-[var(--radius-xl)]" />;
  }

  if (!data) {
    return (
      <EmptyState
        icon={MessageSquareText}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  const summary: readonly { key: string; value: number }[] = [
    { key: "active", value: data.active_student_count },
    { key: "responded", value: data.responded_count },
    { key: "missed", value: data.missed_count },
  ];

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        {summary.map((item) => (
          <div
            key={item.key}
            className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5"
          >
            <p className="text-[22px] font-bold leading-none tabular-nums text-[var(--color-text)]">
              {item.value}
            </p>
            <p className="mt-1 text-[12px] text-[var(--color-text-muted)]">
              {t(`summary.${item.key}`)}
            </p>
          </div>
        ))}
      </div>

      <ol className="space-y-3">
        {data.cards.map((card, index) => (
          <CardResult key={card.card_id} card={card} position={index + 1} />
        ))}
      </ol>
    </section>
  );
}

interface CardResultProps {
  readonly card: CheckpointCardResult;
  readonly position: number;
}

function CardResult({ card, position }: CardResultProps) {
  const t = useTranslations("teacher.results");
  const isFinal = card.kind === "final_comments";
  const maxBucket = Math.max(
    1,
    ...CONFIDENCE_KEYS.map((k) => card.confidence_distribution[k] ?? 0)
  );

  return (
    <li className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-start gap-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-primary-light)] text-[12px] font-semibold text-[var(--color-primary-hover)]">
          {position}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[13px] leading-relaxed text-[var(--color-text)]">
            {card.prompt}
          </p>
          <Badge variant="outline">
            {isFinal ? t("kind.final_comments") : t("kind.review_point")}
          </Badge>
        </div>
        <span className="shrink-0 text-[12px] text-[var(--color-text-muted)]">
          {t("responseCount", { count: card.response_count })}
        </span>
      </div>

      {isFinal ? (
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("textResponses", { count: card.text_response_count })}
        </p>
      ) : (
        <div
          className="space-y-1.5"
          aria-label={t("distributionLabel")}
        >
          {CONFIDENCE_KEYS.map((key) => {
            const count = card.confidence_distribution[key] ?? 0;
            const pct = Math.round((count / maxBucket) * 100);
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="w-8 shrink-0 text-right text-[12px] font-medium tabular-nums text-[var(--color-text-secondary)]">
                  {key}
                </span>
                <div className="h-3 flex-1 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]">
                  <div
                    className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)]"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="w-6 shrink-0 text-[12px] tabular-nums text-[var(--color-text-muted)]">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </li>
  );
}
