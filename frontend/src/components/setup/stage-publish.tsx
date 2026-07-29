"use client";

import { useCallback } from "react";

import { StepReview } from "@/components/setup/step-review";
import { stageForStep, type SetupStage } from "@/lib/setup-stages";
import type { SetupStepKey } from "@/hooks/use-setup";

interface StagePublishProps {
  readonly courseId: string;
  readonly onNavigate: (stage: SetupStage) => void;
}

/**
 * Stage 5 of 5: Review and publish.
 *
 * Owns no step flag: publishing is the action, not a checklist item. T026
 * (ready) and T028 (blocked) are states of this one screen, per the approved
 * variant merge, and readiness is state rather than a new route.
 *
 * When the blocked state offers "go fix this", it names a backend STEP; this
 * stage translates that into the STAGE that owns it, so the user is returned to
 * a surface they recognise rather than to an internal step id. The step's own
 * position inside that stage is preserved because nothing was discarded on the
 * way here.
 */
export function StagePublish({ courseId, onNavigate }: StagePublishProps) {
  const handleNavigate = useCallback(
    (step: SetupStepKey) => onNavigate(stageForStep(step)),
    [onNavigate]
  );

  return <StepReview courseId={courseId} onNavigate={handleNavigate} />;
}
