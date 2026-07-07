"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCheckpointIntro,
  useRevisitResponse,
  type RevisitResponseResult,
  type StudentCheckpointCard,
} from "@/hooks/use-checkpoints";
import { usePilotConfig } from "@/hooks/use-pilot-config";

import { ConfidenceCard } from "./confidence-card";

interface RevisitRunnerProps {
  /** The follow-up (`follow_up`-kind) checkpoint being revisited. */
  readonly checkpointId: string;
  /** Leave the revisit (back to history). */
  readonly onDone: () => void;
}

/**
 * S041 — the revisit response. Re-answers the follow-up checkpoint's review
 * points with the shared `ConfidenceCard`, submitting each via
 * `useRevisitResponse` (which echoes a before/after confidence delta). After the
 * last card, a success banner reports whether confidence improved. Only
 * `review_point` cards are revisited — a follow-up carries no final-comments card.
 */
export function RevisitRunner({ checkpointId, onDone }: RevisitRunnerProps) {
  const t = useTranslations("student.checkpoint.revisit");
  const intro = useCheckpointIntro(checkpointId);
  const { config } = usePilotConfig();
  const revisit = useRevisitResponse(checkpointId);

  const [index, setIndex] = useState(0);
  const [confidence, setConfidence] = useState<Record<string, number>>({});
  const [done, setDone] = useState(false);
  const [lastResult, setLastResult] = useState<RevisitResponseResult | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);

  const reviewCards = useMemo(
    () => (intro.data?.cards ?? []).filter((c) => c.kind === "review_point"),
    [intro.data]
  );
  const total = reviewCards.length;

  const submitCard = useCallback(
    async (card: StudentCheckpointCard, value: number) => {
      setError(null);
      try {
        const res = await revisit.mutateAsync({
          card_id: card.id,
          confidence: value,
        });
        setLastResult(res);
        if (index + 1 < total) {
          setIndex((i) => i + 1);
        } else {
          setDone(true);
        }
      } catch {
        setError(t("submitError"));
      }
    },
    [index, revisit, t, total]
  );

  if (intro.isLoading || !config) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (intro.isError || total === 0) {
    return (
      <StateBanner
        tone="warning"
        title={t("loadErrorTitle")}
        reason={t("loadErrorReason")}
      />
    );
  }

  if (done) {
    const improved = (lastResult?.delta ?? 0) > 0;
    return (
      <div className="space-y-6">
        <StateBanner
          tone="success"
          title={t("doneTitle")}
          reason={
            improved && lastResult?.delta != null
              ? t("improved", { delta: lastResult.delta })
              : t("same")
          }
        />
        <Button type="button" size="lg" onClick={onDone}>
          {t("backToHistory")}
        </Button>
      </div>
    );
  }

  const scale = config.confidence_scale;
  const card = reviewCards[index];

  return (
    <div className="space-y-4">
      {error ? <StateBanner tone="warning" title={error} /> : null}
      <ConfidenceCard
        key={card.id}
        prompt={card.prompt}
        current={index + 1}
        total={total}
        scale={scale}
        value={confidence[card.id] ?? null}
        onChange={(v) => setConfidence((prev) => ({ ...prev, [card.id]: v }))}
        onNext={() => submitCard(card, confidence[card.id]!)}
        onBack={index > 0 ? () => setIndex((i) => Math.max(0, i - 1)) : undefined}
        isSubmitting={revisit.isPending}
        question={t("question")}
        nextLabel={index + 1 < total ? t("next") : t("submit")}
      />
    </div>
  );
}
