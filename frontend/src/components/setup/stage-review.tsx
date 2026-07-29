"use client";

import { useCallback } from "react";

import { StepIlo } from "@/components/setup/step-ilo";
import { StepCheckpoints } from "@/components/setup/step-checkpoints";
import { StepScorePolicy } from "@/components/setup/step-score-policy";
import { StepClassCode } from "@/components/setup/step-class-code";
import { StepMemoryImport } from "@/components/setup/step-memory-import";

interface StageReviewProps {
  readonly courseId: string;
  readonly onSaved: () => void;
  readonly onAdvance: () => void;
}

/**
 * Stage 4 of 5: Review course context.
 *
 * Absorbs four backend steps (`ilo_map`, `checkpoints`, `score_policy`,
 * `class_code`). They belong together because they are one user task: confirm
 * what Meli derived from the sources before anyone else sees it. Each keeps its
 * own server flag, so publish gating is unchanged and a half-reviewed course
 * still cannot publish.
 *
 * T019 (summary) and T020 (outcomes expanded) are view states of this same
 * stage, which is the approved variant merge: "View state only; back/forward
 * preserves stage ownership."
 */
export function StageReview({
  courseId,
  onSaved,
  onAdvance,
}: StageReviewProps) {
  const handleFinal = useCallback(() => {
    onSaved();
    onAdvance();
  }, [onSaved, onAdvance]);

  return (
    <div className="space-y-10">
      <StepIlo courseId={courseId} onComplete={onSaved} />
      <StepCheckpoints courseId={courseId} onComplete={onSaved} />
      <StepScorePolicy courseId={courseId} onComplete={onSaved} />
      <StepClassCode courseId={courseId} onComplete={handleFinal} />

      {/*
        Previous-term memory import is not a step flag and never gates publish.
        It self-hides when this course has no earlier offering to carry forward.
      */}
      <StepMemoryImport courseId={courseId} />
    </div>
  );
}
