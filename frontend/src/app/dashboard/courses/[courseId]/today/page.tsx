// frontend/src/app/dashboard/courses/[courseId]/today/page.tsx
"use client";
import { use } from "react";

import { NextActionList } from "@/components/decision/next-action-list";

export default function TodayPage(
  props: { readonly params: Promise<{ readonly courseId: string }> },
) {
  const { courseId } = use(props.params);
  return (
    <main className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-[var(--color-text)]">Today</h1>
        <p className="text-sm text-[var(--color-muted)]">
          The next things worth doing — based on what you&apos;ve already mastered.
        </p>
      </header>
      <NextActionList courseId={courseId} />
    </main>
  );
}
