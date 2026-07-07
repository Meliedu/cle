"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";

/** Why S004 is showing: an unknown/mistyped code, or a deactivated one. */
export type InvalidCodeReason = "not_found" | "inactive";

interface StateInvalidCodeProps {
  readonly reason: InvalidCodeReason;
  /** Return to S003 to try a different code. */
  readonly onTryAgain: () => void;
  /** Leave the funnel (back to the student's courses). */
  readonly onBackToCourses: () => void;
}

/**
 * S004 — invalid / inactive join code. One blocked treatment (a `StateBanner`)
 * with reason-specific copy: `not_found` (no course matches) vs `inactive` (a
 * real code the teacher turned off). Offers "try again" (→ S003) and a way out.
 */
export function StateInvalidCode({
  reason,
  onTryAgain,
  onBackToCourses,
}: StateInvalidCodeProps) {
  const t = useTranslations("student.join");

  return (
    <div className="space-y-6">
      <StateBanner
        tone="blocked"
        title={t("invalid.title")}
        reason={
          reason === "inactive"
            ? t("invalid.reasonInactive")
            : t("invalid.reasonNotFound")
        }
      />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="button" size="lg" onClick={onTryAgain}>
          {t("invalid.tryAgain")}
        </Button>
        <Button
          type="button"
          size="lg"
          variant="outline"
          onClick={onBackToCourses}
        >
          {t("invalid.backToCourses")}
        </Button>
      </div>
    </div>
  );
}
