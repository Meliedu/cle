"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";

interface StateJoinSuccessProps {
  /** The course the student just joined (shown in the headline). */
  readonly courseName: string;
  /** Enter the course workspace. */
  readonly onOpenCourse: () => void;
  /** Head to the student dashboard instead. */
  readonly onDashboard: () => void;
}

/**
 * S013 — join success. The terminal happy path: the student landed an `active`
 * enrollment (join_mode=code), so the workspace is theirs. One success
 * treatment (a `StateBanner`) naming the course, then the two next actions from
 * the design — open the course (primary) or go to the dashboard.
 */
export function StateJoinSuccess({
  courseName,
  onOpenCourse,
  onDashboard,
}: StateJoinSuccessProps) {
  const t = useTranslations("student.join");

  return (
    <div className="space-y-6">
      <StateBanner
        tone="success"
        title={t("success.title", { course: courseName })}
        reason={t("success.reason")}
      />

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="button" size="lg" onClick={onOpenCourse}>
          {t("success.openCourse")}
        </Button>
        <Button
          type="button"
          size="lg"
          variant="outline"
          onClick={onDashboard}
        >
          {t("success.dashboard")}
        </Button>
      </div>
    </div>
  );
}
