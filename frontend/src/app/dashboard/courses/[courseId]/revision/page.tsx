"use client";

import { use } from "react";
import { RevisionPlayer } from "@/components/revision/revision-player";

export default function RevisionPage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(params);
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold" style={{ color: "var(--color-text)" }}>
        Revision Practice
      </h1>
      <RevisionPlayer courseId={courseId} />
    </div>
  );
}
