"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import type { CommentReactionResponsePayload } from "@/hooks/use-activities";
import type { ReactionEntry } from "./activity-format";

interface CommentReactionActivityProps {
  /** Available reactions from the activity `config.reactions`. */
  readonly reactions: readonly string[];
  /** The student's own stacked reactions so far (server STACKS these). */
  readonly entries: readonly ReactionEntry[];
  readonly onSubmit: (payload: CommentReactionResponsePayload) => Promise<unknown>;
  readonly isSubmitting: boolean;
}

/**
 * S056 — the comment/reaction. The student taps a reaction to post `{reaction}`;
 * the server STACKS each one onto their response row, so the same student can
 * react multiple times. The stacked entries render beneath the reaction row as
 * a running list of what they've added.
 */
export function CommentReactionActivity({
  reactions,
  entries,
  onSubmit,
  isSubmitting,
}: CommentReactionActivityProps) {
  const t = useTranslations("student.activities.comment");

  return (
    <div className="space-y-5">
      <div className="space-y-2.5">
        <p className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
          {t("instructions")}
        </p>
        <div className="flex flex-wrap gap-2">
          {reactions.map((reaction) => (
            <Button
              key={reaction}
              type="button"
              variant="outline"
              size="lg"
              disabled={isSubmitting}
              onClick={() => onSubmit({ reaction })}
              className="h-11 gap-2 px-4 text-[14px]"
            >
              <span aria-hidden={false}>{reaction}</span>
            </Button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("yourReactions")}
        </p>
        {entries.length === 0 ? (
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("empty")}
          </p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {entries.map((entry, i) => (
              <li
                key={`${entry.reaction}-${i}`}
                className="inline-flex items-center rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3 py-1 text-[13px] text-[var(--color-text)]"
              >
                {entry.reaction}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
