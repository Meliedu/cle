// frontend/src/app/dashboard/courses/[courseId]/engine/page.tsx
"use client";
import { use } from "react";

import { EngineModeSelector } from "@/components/decision/engine-mode-selector";

export default function EnginePage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">
          Adaptive engine
        </h1>
        <p className="text-sm text-[var(--color-muted)]">
          Choose how aggressively Meli surfaces personalised next-actions for this course.
        </p>
      </header>
      <EngineModeSelector courseId={courseId} />
    </main>
  );
}
