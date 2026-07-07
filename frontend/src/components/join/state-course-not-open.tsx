"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";

interface StateCourseNotOpenProps {
  /** The course that isn't published yet (shown in the copy). */
  readonly courseName: string;
  /** Re-enter a code (the instructor may have just opened access). */
  readonly onTryAgain: () => void;
  /** Leave the funnel (back to the student's courses). */
  readonly onBackToCourses: () => void;
}

/**
 * S012 — course not open yet. The server refused the join with
 * `SETUP_NOT_OPEN` (the instructor hasn't published setup). This is terminal
 * for now: a `warning` banner explaining the course isn't ready, plus a way
 * back and a "try again" once access opens. No route into the workspace — a
 * non-open course has nothing to read.
 */
export function StateCourseNotOpen({
  courseName,
  onTryAgain,
  onBackToCourses,
}: StateCourseNotOpenProps) {
  const t = useTranslations("student.join");

  return (
    <div className="space-y-6">
      <StateBanner
        tone="warning"
        title={t("notOpen.title")}
        reason={t("notOpen.reason", { course: courseName })}
      />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="button" size="lg" onClick={onBackToCourses}>
          {t("notOpen.backToCourses")}
        </Button>
        <Button type="button" size="lg" variant="outline" onClick={onTryAgain}>
          {t("notOpen.tryAgain")}
        </Button>
      </div>
    </div>
  );
}
