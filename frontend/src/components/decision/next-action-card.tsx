// frontend/src/components/decision/next-action-card.tsx
"use client";
import type { NextAction } from "@/lib/decision-types";

interface Props {
  readonly action: NextAction;
  readonly onClick: () => void;
  readonly busy: boolean;
}

const ACTION_LABELS: Record<NextAction["action_type"], string> = {
  review_concept: "Review concept",
  prep_meeting: "Prep for meeting",
  complete_assignment: "Complete assignment",
  do_quiz: "Take quiz",
  practice_weakness: "Practice weakness",
  catch_up_reading: "Catch up reading",
  flashcard_review: "Review flashcards",
  pronunciation_practice: "Pronunciation practice",
  watch_recording: "Watch recording",
};

function describeTarget(action: NextAction): string {
  const r = action.reason as Record<string, string | undefined>;
  return (
    r.concept_name ?? r.assignment_title ?? r.meeting_title ?? "—"
  );
}

export function NextActionCard({ action, onClick, busy }: Props) {
  const score = parseFloat(action.priority_score);
  const isHighPriority = score >= 3.0;
  return (
    <article
      className="space-y-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
      data-testid="next-action-card"
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {ACTION_LABELS[action.action_type]}
        </h3>
        <span
          className={
            "text-xs " +
            (isHighPriority
              ? "text-[var(--color-warning)]"
              : "text-[var(--color-muted)]")
          }
        >
          priority {score.toFixed(2)}
        </span>
      </header>
      <p className="text-sm text-[var(--color-text)]">{describeTarget(action)}</p>
      <button
        type="button"
        disabled={busy}
        onClick={onClick}
        className="rounded bg-[var(--color-accent)] px-3 py-1 text-xs text-[var(--color-on-accent)] disabled:opacity-50"
      >
        {busy ? "Opening…" : "Start"}
      </button>
    </article>
  );
}
