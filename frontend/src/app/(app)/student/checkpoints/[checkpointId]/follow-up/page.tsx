"use client";

import { use } from "react";
import { useSearchParams } from "next/navigation";

import { FollowUpFlow } from "@/components/checkpoint/follow-up-flow";

interface FollowUpPageProps {
  /** Next.js 16 passes route params as a Promise; unwrap with `use()`. */
  readonly params: Promise<{ checkpointId: string }>;
}

/**
 * `/student/checkpoints/{checkpointId}/follow-up` — the follow-up + revisit loop
 * (S040 → S041). An optional `?course={id}` query lets the "back" actions return
 * to that course's checkpoint history. Mobile-first single column.
 */
export default function FollowUpPage({ params }: FollowUpPageProps) {
  const { checkpointId } = use(params);
  const searchParams = useSearchParams();
  const courseId = searchParams.get("course") ?? undefined;

  return (
    <div className="mx-auto w-full max-w-md space-y-6 py-2">
      <FollowUpFlow checkpointId={checkpointId} courseId={courseId} />
    </div>
  );
}
