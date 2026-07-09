"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCourses } from "@/hooks/use-courses";

import { CourseInsightsView } from "./course-insights-view";

/**
 * Top-level `/teacher/insights` body: a course selector that drives the shared
 * `CourseInsightsView`. The per-course workspace tab renders the same view
 * inside `CourseWorkspaceShell`; this browser is the cross-course entry point
 * for an instructor who has not drilled into a specific course yet.
 */
export function TeacherInsightsBrowser() {
  const t = useTranslations("teacher.insights");
  const { data: courses, isLoading } = useCourses();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (isLoading) {
    return <Skeleton className="h-10 w-64" />;
  }

  if (!courses || courses.length === 0) {
    return <EmptyState variant="empty" title={t("picker.empty")} />;
  }

  // Default to the first course so the instructor lands on evidence immediately.
  const activeId = selectedId ?? courses[0].id;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="insights-course"
          className="text-[12px] font-medium text-[var(--color-text-muted)]"
        >
          {t("picker.label")}
        </label>
        <Select
          value={activeId}
          onValueChange={(val) => setSelectedId((val as string | null) ?? null)}
        >
          <SelectTrigger id="insights-course" className="w-full max-w-xs">
            {/* base-ui Select.Value renders the raw value by default; map the
                selected course id back to its display name. */}
            <SelectValue placeholder={t("picker.placeholder")}>
              {(value) =>
                courses.find((c) => c.id === value)?.name ??
                t("picker.placeholder")
              }
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {courses.map((course) => (
              <SelectItem key={course.id} value={course.id}>
                {course.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <CourseInsightsView key={activeId} courseId={activeId} />
    </div>
  );
}
