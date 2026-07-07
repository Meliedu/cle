"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { FollowUpSuggested } from "./follow-up-suggested";
import { RevisitRunner } from "./revisit-runner";

interface FollowUpFlowProps {
  /** The checkpoint whose weak points drive the follow-up + revisit. */
  readonly checkpointId: string;
  /** Optional course id to route back to that course's history. */
  readonly courseId?: string;
}

type FollowUpStep = "suggested" | "revisit";

/**
 * Client orchestrator for the follow-up loop: S040 (suggested) → S041 (revisit).
 * The suggestion motivates the revisit; starting it swaps to the revisit runner,
 * which ends with a confidence-delta receipt and a route back to history.
 */
export function FollowUpFlow({ checkpointId, courseId }: FollowUpFlowProps) {
  const router = useRouter();
  const [step, setStep] = useState<FollowUpStep>("suggested");

  const backToHistory = useCallback(() => {
    router.push(
      courseId ? `/student/courses/${courseId}/checkpoints` : "/student/courses"
    );
  }, [courseId, router]);

  if (step === "revisit") {
    return <RevisitRunner checkpointId={checkpointId} onDone={backToHistory} />;
  }

  return (
    <FollowUpSuggested
      checkpointId={checkpointId}
      onStart={() => setStep("revisit")}
      onViewHistory={backToHistory}
    />
  );
}
