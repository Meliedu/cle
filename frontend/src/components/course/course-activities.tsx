"use client";

import { useTranslations } from "next-intl";
import { Sparkles } from "lucide-react";

import { EmptyState } from "@/components/patterns";

interface CourseActivitiesProps {
  readonly courseId: string;
}

/**
 * T074 — teacher Activities home. F1 ships the route shell + a designed
 * placeholder; F2–F6 fill it with the practice / graded-quiz / swipe-vote-comment
 * builders, the live monitor, and the fold-in entry points. `courseId` is
 * accepted now so those tasks query without a route/signature change.
 */
export function CourseActivities({ courseId }: CourseActivitiesProps) {
  const t = useTranslations("teacher.activities");
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
