"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCheckpointIntro,
  useSubmitCheckpointResponse,
  type AttendanceStatus,
  type StudentCheckpointCard,
} from "@/hooks/use-checkpoints";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import { ApiError } from "@/lib/api";

import { AttendanceConfirmed } from "./attendance-confirmed";
import { CheckpointComplete } from "./checkpoint-complete";
import { CheckpointIntro } from "./checkpoint-intro";
import { CheckpointMissed } from "./checkpoint-missed";
import { ConfidenceCard } from "./confidence-card";
import { FinalCommentsCard } from "./final-comments-card";

/** Attendance context from an upstream QR scan (attend flow), when present. */
export interface RunnerAttendance {
  readonly status: AttendanceStatus;
  readonly checkedInAt: string | null;
}

interface CheckpointRunnerProps {
  readonly checkpointId: string;
  /** Course id so a submission invalidates the student's history cache (S039). */
  readonly courseId?: string;
  /** Attendance already recorded upstream (a successful scan). Drives S038/S042. */
  readonly attendance?: RunnerAttendance;
  /** Leave the checkpoint (back to the session / courses). */
  readonly onExit: () => void;
  /** Open the student's checkpoint history (S039). */
  readonly onViewHistory: () => void;
}

type RunnerStep = "intro" | "cards" | "complete";

/**
 * Orchestrates the student checkpoint flow S034 → S037: intro, then one
 * confidence card at a time for each `review_point`, then the optional
 * `final_comments` card, then the submitted receipt. Each card is submitted as
 * its own response on advance (mirroring the backend's per-card model); the
 * confidence value is required, the final comment is optional (an empty comment
 * is simply not submitted, since the backend rejects blank final text).
 */
export function CheckpointRunner({
  checkpointId,
  courseId,
  attendance,
  onExit,
  onViewHistory,
}: CheckpointRunnerProps) {
  const t = useTranslations("student.checkpoint");
  const intro = useCheckpointIntro(checkpointId);
  const { config } = usePilotConfig();
  const submit = useSubmitCheckpointResponse(checkpointId, courseId);

  const [step, setStep] = useState<RunnerStep>("intro");
  const [index, setIndex] = useState(0);
  const [confidence, setConfidence] = useState<Record<string, number>>({});
  const [finalText, setFinalText] = useState("");
  const [submittedAt, setSubmittedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { reviewCards, finalCard } = useMemo(() => {
    const cards = intro.data?.cards ?? [];
    return {
      reviewCards: cards.filter((c) => c.kind === "review_point"),
      finalCard: cards.find((c) => c.kind === "final_comments") ?? null,
    };
  }, [intro.data]);

  // Total flow steps = every review card + the final card (when present).
  const total = reviewCards.length + (finalCard ? 1 : 0);
  const onFinalStep = finalCard !== null && index === reviewCards.length;

  const advanceOrFinish = useCallback(
    (submittedTs: string | null) => {
      if (index + 1 < total) {
        setIndex((i) => i + 1);
        return;
      }
      setSubmittedAt(submittedTs);
      setStep("complete");
    },
    [index, total]
  );

  const submitConfidence = useCallback(
    async (card: StudentCheckpointCard, value: number) => {
      setError(null);
      try {
        const res = await submit.mutateAsync({
          card_id: card.id,
          confidence: value,
        });
        advanceOrFinish(res.submitted_at);
      } catch {
        setError(t("card.submitError"));
      }
    },
    [advanceOrFinish, submit, t]
  );

  const submitFinal = useCallback(async () => {
    setError(null);
    const text = finalText.trim();
    // The backend rejects a blank final comment, and the card is optional — so
    // skip the submission entirely when nothing was written.
    if (!finalCard || text === "") {
      setSubmittedAt(null);
      setStep("complete");
      return;
    }
    try {
      const res = await submit.mutateAsync({
        card_id: finalCard.id,
        text_response: text,
      });
      setSubmittedAt(res.submitted_at);
      setStep("complete");
    } catch {
      setError(t("final.submitError"));
    }
  }, [finalCard, finalText, submit, t]);

  // ----- loading / error / empty -----

  if (intro.isLoading || !config) {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-lg)]" />
        <Skeleton className="h-11 w-full rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (intro.isError || !intro.data) {
    // A closed / out-of-window checkpoint 409s `QR_NOT_AVAILABLE` — that's the
    // missed / late terminal (S038), not a generic failure. Attendance from an
    // upstream scan means the miss is "late" (checked in) rather than absent.
    const closed =
      intro.error instanceof ApiError &&
      (intro.error.code === "QR_NOT_AVAILABLE" || intro.error.status === 409);
    if (closed) {
      return (
        <CheckpointMissed
          submittedCount={0}
          totalCount={0}
          closedAt={null}
          attendanceRecorded={Boolean(attendance)}
          onBackToSession={onExit}
          onViewHistory={onViewHistory}
        />
      );
    }
    return (
      <StateBanner
        tone="warning"
        title={t("intro.loadErrorTitle")}
        reason={t("intro.loadErrorReason")}
      />
    );
  }

  if (total === 0) {
    // Attendance is already recorded (scan) but there's nothing to answer —
    // show the attendance receipt (S042) rather than an empty prompt.
    if (attendance) {
      return (
        <AttendanceConfirmed
          status={attendance.status}
          checkedInAt={attendance.checkedInAt}
          onBackToSession={onExit}
        />
      );
    }
    return (
      <StateBanner
        tone="info"
        title={t("intro.emptyTitle")}
        reason={t("intro.emptyReason")}
      />
    );
  }

  const scale = config.confidence_scale;

  // ----- render by step -----

  if (step === "intro") {
    return (
      <CheckpointIntro
        intro={intro.data}
        onStart={() => setStep("cards")}
        onBack={onExit}
      />
    );
  }

  if (step === "complete") {
    return (
      <CheckpointComplete
        reviewPointCount={reviewCards.length}
        hasComment={Boolean(finalCard) && finalText.trim() !== ""}
        submittedAt={submittedAt}
        onBackToSession={onExit}
        onViewHistory={onViewHistory}
      />
    );
  }

  // step === "cards"
  return (
    <div className="space-y-4">
      {error ? <StateBanner tone="warning" title={error} /> : null}

      {onFinalStep && finalCard ? (
        <FinalCommentsCard
          prompt={finalCard.prompt}
          current={index + 1}
          total={total}
          value={finalText}
          onChange={setFinalText}
          onSubmit={submitFinal}
          onBack={() => setIndex((i) => Math.max(0, i - 1))}
          isSubmitting={submit.isPending}
        />
      ) : (
        (() => {
          const card = reviewCards[index];
          return (
            <ConfidenceCard
              key={card.id}
              prompt={card.prompt}
              current={index + 1}
              total={total}
              scale={scale}
              value={confidence[card.id] ?? null}
              onChange={(v) =>
                setConfidence((prev) => ({ ...prev, [card.id]: v }))
              }
              onNext={() => submitConfidence(card, confidence[card.id]!)}
              onBack={
                index > 0
                  ? () => setIndex((i) => Math.max(0, i - 1))
                  : undefined
              }
              isSubmitting={submit.isPending}
              question={t("card.question")}
              nextLabel={t("card.next")}
            />
          );
        })()
      )}
    </div>
  );
}
