"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, Sparkles } from "lucide-react";

import { EmptyState, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useLearningProfile,
  type ConceptMasteryEntry,
} from "@/hooks/use-insights";

import { ConceptEvidencePanel } from "./concept-evidence-panel";

interface LearningProfileViewProps {
  readonly courseId: string;
}

type GroupKey = "strong" | "developing" | "weak";

const GROUP_ORDER: readonly GroupKey[] = ["strong", "developing", "weak"];

/** Left-accent tone per group — reinforced by the group label, never color-only. */
const GROUP_ACCENT: Record<GroupKey, string> = {
  strong: "border-l-[var(--color-success)]",
  developing: "border-l-[var(--color-accent)]",
  weak: "border-l-[var(--color-warning)]",
};

/**
 * S062 — student learning profile. Reshapes `concept_mastery` into strong /
 * developing / weak groups (`useLearningProfile`, pure read). A profile with no
 * confident evidence renders the designed no-evidence state (S070) — never a
 * blank div and never a fabricated score (Decision 6). Each concept expands its
 * own evidence panel ("where did this come from"). The pilot disclaimer is shown
 * verbatim from the payload.
 */
export function LearningProfileView({ courseId }: LearningProfileViewProps) {
  const t = useTranslations("student.profile");
  const { data, isLoading, isError } = useLearningProfile(courseId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  if (!data.has_evidence) {
    return (
      <div className="space-y-6">
        <EmptyState
          variant="waiting"
          title={t("empty.title")}
          reason={t("empty.reason")}
        />
        <p className="text-center text-[12px] leading-relaxed text-[var(--color-text-muted)]">
          {data.disclaimer}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {GROUP_ORDER.map((key) => {
        const entries = data.groups[key];
        if (entries.length === 0) return null;
        return (
          <section key={key} className="space-y-2">
            <h2 className="flex items-center gap-2 text-[13px] font-semibold text-[var(--color-text)]">
              <Sparkles
                aria-hidden="true"
                className="size-4 text-[var(--color-text-muted)]"
              />
              {t(`groups.${key}`)}
              <span className="text-[12px] font-normal text-[var(--color-text-muted)]">
                ({entries.length})
              </span>
            </h2>
            <ul className="space-y-2">
              {entries.map((entry) => (
                <ConceptRow
                  key={entry.concept_id}
                  entry={entry}
                  accent={GROUP_ACCENT[key]}
                />
              ))}
            </ul>
          </section>
        );
      })}

      <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
        {data.disclaimer}
      </p>
    </div>
  );
}

interface ConceptRowProps {
  readonly entry: ConceptMasteryEntry;
  readonly accent: string;
}

/** One concept: a tappable header that expands its evidence panel below. */
function ConceptRow({ entry, accent }: ConceptRowProps) {
  const t = useTranslations("student.profile");
  const [open, setOpen] = useState(false);

  return (
    <li
      className={cn(
        "overflow-hidden rounded-[var(--radius-xl)] border border-l-4 border-[var(--color-border)] bg-[var(--color-surface)]",
        accent
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
      >
        <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-[var(--color-text)]">
          {entry.concept_name}
        </span>
        <span className="tabular-nums text-[13px] font-medium text-[var(--color-text-secondary)]">
          {Math.round(entry.mastery_score * 100)}%
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] motion-reduce:transition-none",
            open && "rotate-180"
          )}
        />
      </button>
      <span className="sr-only">{open ? t("collapse") : t("expand")}</span>
      {open ? <ConceptEvidencePanel entry={entry} /> : null}
    </li>
  );
}
