"use client";

import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";

/** One skill result, mirroring the backend `_skill_evidence` row. */
export interface SkillEvidence {
  readonly skill: string;
  readonly state: "ready" | "developing" | "needs_support";
  readonly score: number;
}

interface PlacementEvidenceProps {
  readonly evidence: readonly SkillEvidence[];
}

/**
 * Evidence behind a placement recommendation (Placement, note 02).
 *
 *   Result connects reading, vocabulary, and listening evidence to the
 *   recommended course and visible support plan.
 *
 * Each row reads left to right as one sentence: this skill, in this state,
 * informs this outcome. That chain is what makes the recommendation
 * reviewable rather than an opaque verdict, which is the whole point of the
 * placement boundary.
 *
 * The raw score is deliberately NOT shown. A learner reading "-1.0" next to
 * "Listening" would reasonably take it for a grade; the state word carries the
 * same information without implying assessment.
 */
export function PlacementEvidence({ evidence }: PlacementEvidenceProps) {
  const t = useTranslations("student.join.recommendation");

  if (evidence.length === 0) {
    return (
      <p className="text-[14px] text-[var(--color-text-muted)]">
        {t("evidenceEmpty")}
      </p>
    );
  }

  const tone: Record<SkillEvidence["state"], string> = {
    ready:
      "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]",
    developing:
      "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-hover)]",
    needs_support:
      "border-[var(--color-error)]/35 bg-[var(--color-error-light)] text-[var(--color-error)]",
  };

  return (
    <ul className="border-t border-[var(--color-border)]">
      {evidence.map((row) => (
        <li
          key={row.skill}
          className="flex flex-col gap-3 border-b border-[var(--color-border)] py-4 sm:flex-row sm:items-center sm:gap-6"
        >
          <div className="flex min-w-0 items-center gap-3 sm:w-[200px] sm:shrink-0">
            <span
              aria-hidden="true"
              className={cn(
                "flex size-9 shrink-0 items-center justify-center rounded-full border text-[13px] font-semibold",
                tone[row.state]
              )}
            >
              {t(`skill.${row.skill}`).charAt(0)}
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] text-[var(--color-text-muted)]">
                {t(`skill.${row.skill}`)}
              </p>
              <p
                className={cn(
                  "text-[15px] font-semibold",
                  row.state === "ready"
                    ? "text-[var(--color-success)]"
                    : row.state === "developing"
                      ? "text-[var(--color-primary-hover)]"
                      : "text-[var(--color-error)]"
                )}
              >
                {t(`state.${row.state}`)}
              </p>
            </div>
          </div>

          {/* What this result informs. Support needs are named as a plan, not
              as a deficit. */}
          <p
            className={cn(
              "min-w-0 flex-1 rounded-[var(--radius-md)] px-4 py-3 text-[14px] leading-relaxed",
              row.state === "needs_support"
                ? "bg-[var(--color-error-light)] text-[var(--color-text)]"
                : row.state === "developing"
                  ? "bg-[var(--color-cream)] text-[var(--color-text)]"
                  : "bg-[var(--color-success-light)] text-[var(--color-text)]"
            )}
          >
            {row.state === "needs_support" ? (
              <span className="mr-2 font-semibold text-[var(--color-error)]">
                {t("supportPlan")}:
              </span>
            ) : null}
            {t(`informs.${row.state}`)}
          </p>
        </li>
      ))}
    </ul>
  );
}
