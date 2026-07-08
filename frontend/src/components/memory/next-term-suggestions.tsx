"use client";

import { useTranslations } from "next-intl";
import { ArrowRightCircle, Sparkles } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import {
  useNextTermSuggestions,
  type NextTermSuggestion,
} from "@/hooks/use-memory";

import { sourceLabel, summaryText } from "./memory-format";

interface NextTermSuggestionsProps {
  readonly courseId: string;
}

/**
 * T080 — next-term suggestions. Lists the `carry_forward` items from earlier
 * offerings of this course (same code lineage + instructor), grouped by their
 * source course. Read-only here — the actual import into a NEW term happens in
 * the setup wizard's memory-import step. A course with no prior-term memory
 * shows a quiet inline message rather than an empty card.
 */
export function NextTermSuggestions({ courseId }: NextTermSuggestionsProps) {
  const t = useTranslations("teacher.memory.suggestions");
  const { data, isLoading, isError } = useNextTermSuggestions(courseId);

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-light)] text-[var(--color-accent)]">
          <Sparkles aria-hidden="true" strokeWidth={1.85} className="size-4" />
        </span>
        <div className="space-y-0.5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : isError ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("loadError")}
        </p>
      ) : !data || data.length === 0 ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">{t("empty")}</p>
      ) : (
        <ul className="space-y-2">
          {data.map((suggestion) => (
            <SuggestionRow key={suggestion.id} suggestion={suggestion} />
          ))}
        </ul>
      )}
    </section>
  );
}

function SuggestionRow({
  suggestion,
}: {
  readonly suggestion: NextTermSuggestion;
}) {
  const text =
    summaryText(suggestion.outcome_summary) ??
    summaryText(suggestion.action_summary) ??
    summaryText(suggestion.relationship_summary) ??
    suggestion.instructor_comment;

  return (
    <li className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)]/40 px-3.5 py-3">
      <ArrowRightCircle
        aria-hidden="true"
        strokeWidth={1.85}
        className="mt-0.5 size-4 shrink-0 text-[var(--color-accent)]"
      />
      <div className="min-w-0 flex-1 space-y-0.5">
        {text ? (
          <p className="text-[13px] leading-relaxed text-[var(--color-text)]">
            {text}
          </p>
        ) : null}
        <p className="text-[11px] text-[var(--color-text-muted)]">
          {sourceLabel(
            suggestion.source_course_code,
            suggestion.source_course_name
          )}
        </p>
      </div>
    </li>
  );
}
