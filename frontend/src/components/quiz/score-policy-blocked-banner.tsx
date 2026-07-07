"use client";

import { useTranslations } from "next-intl";
import { CircleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import type { ScorePolicyField } from "@/components/quiz/score-policy-panel";

/** The gated fields the backend enumerates in `SCORE_POLICY_INCOMPLETE.missing[]`. */
const KNOWN_FIELDS: readonly ScorePolicyField[] = [
  "score_category_id",
  "points",
  "grading_mode",
  "deadline",
];

function isKnownField(value: string): value is ScorePolicyField {
  return (KNOWN_FIELDS as readonly string[]).includes(value);
}

interface ScorePolicyBlockedBannerProps {
  /** `ScorePolicyError.missing` — the fields that block a graded publish. */
  readonly missing: readonly string[];
  /** Focus / scroll the score-policy panel to the field that fixes an item. */
  readonly onJump?: (field: ScorePolicyField) => void;
}

/**
 * The blocked state for a gated graded publish (Decision 7 hard gate, spec
 * §3.4). Mirrors P1's `SetupMissingSourceError`: a `StateBanner tone="blocked"`
 * plus one row per `missing[]` field with a jump-to-field affordance so the
 * teacher can resolve each gap in place. Unknown/duplicate codes are filtered so
 * a backend addition never renders a raw enum string.
 */
export function ScorePolicyBlockedBanner({
  missing,
  onJump,
}: ScorePolicyBlockedBannerProps) {
  const t = useTranslations("teacher.quiz.blocked");

  const fields = KNOWN_FIELDS.filter((f) => missing.includes(f));

  return (
    <div className="space-y-3">
      <StateBanner
        tone="blocked"
        title={t("title")}
        reason={t("reason")}
      />

      {fields.length > 0 ? (
        <ul aria-label={t("title")} className="space-y-2">
          {fields.map((field) => (
            <li
              key={field}
              className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-error)]/30 bg-[var(--color-error-light)] p-3"
            >
              <div className="flex min-w-0 gap-2.5">
                <CircleAlert
                  aria-hidden="true"
                  strokeWidth={1.85}
                  className="mt-0.5 size-4 shrink-0 text-[var(--color-error)]"
                />
                <div className="min-w-0 space-y-0.5">
                  <p className="text-[13px] font-medium text-[var(--color-text)]">
                    {t(`field.${field}.label`)}
                  </p>
                  <p className="text-[12px] leading-snug text-[var(--color-text-secondary)]">
                    {t(`field.${field}.hint`)}
                  </p>
                </div>
              </div>
              {onJump ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="shrink-0"
                  onClick={() => onJump(field)}
                >
                  {t("fix")}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export { isKnownField };
