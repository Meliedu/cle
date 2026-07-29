"use client";

import { useCallback, useState } from "react";

import { StepSchedule } from "@/components/setup/step-schedule";
import { StepSessions } from "@/components/setup/step-sessions";

interface StageScheduleProps {
  readonly courseId: string;
  readonly onSaved: () => void;
  readonly onAdvance: () => void;
}

/**
 * Stage 3 of 5: Schedule.
 *
 * Two screens under one backend flag. T018 is the schedule-and-venue editor;
 * T021 is the generated-session review that confirms what the editor produced.
 * There is deliberately no separate `sessions` step key: the editor flips the
 * `schedule` flag and the review folds under it, which is exactly the "keep
 * sub-state in the data model" rule.
 *
 * Both screens are preserved as distinct states; only their promotion to
 * top-level steps is removed.
 */
export function StageSchedule({
  courseId,
  onSaved,
  onAdvance,
}: StageScheduleProps) {
  const [phase, setPhase] = useState<"edit" | "review">("edit");

  const handleEditorComplete = useCallback(() => {
    onSaved();
    setPhase("review");
  }, [onSaved]);

  const handleReviewComplete = useCallback(() => {
    onSaved();
    onAdvance();
  }, [onSaved, onAdvance]);

  if (phase === "review") {
    return (
      <StepSessions
        courseId={courseId}
        onEdit={() => setPhase("edit")}
        onComplete={handleReviewComplete}
      />
    );
  }

  return <StepSchedule courseId={courseId} onComplete={handleEditorComplete} />;
}
