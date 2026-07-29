"use client";

import { useCallback } from "react";

import { StepBasics } from "@/components/setup/step-basics";

interface StageBasicsProps {
  readonly courseId: string;
  readonly onSaved: () => void;
  readonly onAdvance: () => void;
}

/**
 * Stage 1 of 5: Basics.
 *
 * One backend step (`basics`), so the stage is a thin wrapper. It exists so
 * every stage has the same shape and the wizard does not special-case one of
 * them. T014 (empty) and T015 (completed) remain the same route and component,
 * differing only by loaded data, which is the approved variant merge.
 */
export function StageBasics({
  courseId,
  onSaved,
  onAdvance,
}: StageBasicsProps) {
  const handleComplete = useCallback(() => {
    onSaved();
    onAdvance();
  }, [onSaved, onAdvance]);

  return <StepBasics courseId={courseId} onComplete={handleComplete} />;
}
