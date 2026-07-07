"use client";

import { use } from "react";

import { CheckpointHistory } from "@/components/checkpoint/checkpoint-history";

interface CheckpointHistoryPageProps {
  /** Next.js 16 passes route params as a Promise; unwrap with `use()`. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/checkpoints` — the student's checkpoint history
 * for one course (S039). Mobile-first single column.
 */
export default function CheckpointHistoryPage({
  params,
}: CheckpointHistoryPageProps) {
  const { courseId } = use(params);

  return (
    <div className="mx-auto w-full max-w-md py-2">
      <CheckpointHistory courseId={courseId} />
    </div>
  );
}
