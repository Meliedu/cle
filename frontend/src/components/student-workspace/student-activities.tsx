"use client";

import { useTranslations } from "next-intl";
import { Sparkles } from "lucide-react";

import { EmptyState } from "@/components/patterns";

interface StudentActivitiesProps {
  readonly courseId: string;
}

/**
 * S031 / S072 — student activities placeholder. Activities (practice, quizzes,
 * polls) are filled in by P5; until then the tab shows a designed "arriving
 * soon" state instead of a blank panel. Kept as its own screen so P5 only swaps
 * the body. `courseId` is accepted now so the P5 fill can query without a
 * route/signature change.
 */
export function StudentActivities({ courseId }: StudentActivitiesProps) {
  const t = useTranslations("student.activities");
  return (
    <EmptyState
      data-course-id={courseId}
      variant="waiting"
      icon={Sparkles}
      title={t("empty.title")}
      reason={t("empty.reason")}
    />
  );
}
