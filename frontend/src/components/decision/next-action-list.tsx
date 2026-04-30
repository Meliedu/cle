// frontend/src/components/decision/next-action-list.tsx
"use client";
import { useRouter } from "next/navigation";

import { NextActionCard } from "@/components/decision/next-action-card";
import {
  useClickNextAction,
  useNextActions,
} from "@/hooks/use-next-actions";
import type { NextAction } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

function buildHref(courseId: string, action: NextAction): string {
  const id = action.target_id;
  switch (action.target_kind) {
    case "quiz":              return `/dashboard/courses/${courseId}/quizzes/${id}`;
    case "flashcard_set":     return `/dashboard/courses/${courseId}/flashcards/${id}`;
    case "course_meeting":    return `/dashboard/courses/${courseId}/meetings/${id}`;
    case "assignment":        return `/dashboard/courses/${courseId}/assignments/${id}`;
    case "concept":           return `/dashboard/courses/${courseId}/concepts/${id}`;
    case "pronunciation_set": return `/dashboard/courses/${courseId}/pronunciation/${id}`;
    // No documents/[id] route exists; documents are surfaced on the course landing page.
    case "document":          return `/dashboard/courses/${courseId}`;
    case "chunk":             return `/dashboard/courses/${courseId}`;
    default:                  return `/dashboard/courses/${courseId}`;
  }
}

export function NextActionList({ courseId }: Props) {
  const router = useRouter();
  const { data, isLoading, error } = useNextActions(courseId);
  const click = useClickNextAction(courseId);

  if (isLoading) return <p className="text-sm text-[var(--color-text-muted)]">Loading…</p>;
  if (error) return <p className="text-sm text-[var(--color-error)]">Failed to load.</p>;
  const list = data ?? [];
  if (list.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No suggested actions right now. Keep going on your own — we&apos;ll pick up signals as you study.
      </p>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {list.map((a) => (
        <li key={a.id}>
          <NextActionCard
            action={a}
            busy={click.isPending}
            onClick={async () => {
              await click.mutateAsync(a.id);
              router.push(buildHref(courseId, a));
            }}
          />
        </li>
      ))}
    </ul>
  );
}
