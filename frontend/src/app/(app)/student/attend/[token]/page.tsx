"use client";

import { use } from "react";

import { CheckpointAttend } from "@/components/checkpoint/checkpoint-attend";

interface AttendPageProps {
  /** Next.js 16 passes route params as a Promise; unwrap with `use()`. */
  readonly params: Promise<{ token: string }>;
}

/**
 * `/student/attend/{token}` — the QR deep link a student lands on after scanning
 * the classroom code. Mobile-first single column: the scan + the whole
 * checkpoint flow live here, driven by `CheckpointAttend`.
 */
export default function AttendPage({ params }: AttendPageProps) {
  const { token } = use(params);

  return (
    <div className="mx-auto w-full max-w-md space-y-6 py-2">
      <CheckpointAttend token={token} />
    </div>
  );
}
