"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";

interface StatePendingApprovalProps {
  /** The course the student requested to join. */
  readonly courseName: string;
  /** Leave the funnel (back to the student's courses). */
  readonly onBackToCourses: () => void;
}

/**
 * Pending-approval terminal state (join_mode=code_plus_approval). The student's
 * enrollment landed `pending`, so they must NOT be routed into the workspace —
 * they can't read it until an instructor approves. We surface a `waiting`
 * banner (matching `JoinCourseDialog`'s pending treatment) and a single way out.
 */
export function StatePendingApproval({
  courseName,
  onBackToCourses,
}: StatePendingApprovalProps) {
  const t = useTranslations("student.join");

  return (
    <div className="space-y-6">
      <StateBanner
        tone="waiting"
        title={t("pending.title")}
        reason={t("pending.reason", { course: courseName })}
      />

      <Button type="button" size="lg" variant="outline" onClick={onBackToCourses}>
        {t("pending.backToCourses")}
      </Button>
    </div>
  );
}
