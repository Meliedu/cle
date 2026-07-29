"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { useTranslations } from "next-intl";

import { useAuth } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import { apiFetch, isAuthError, type ApiEnvelope } from "@/lib/api";
import { workItemKeys, type ChecklistItem } from "@/hooks/use-work-items";
import {
  buildActions,
  resolveLearningDay,
  type LearningAction,
  type LearningDay,
} from "@/lib/learning-path";

export interface LearningPathResult extends LearningDay {
  readonly all: readonly LearningAction[];
  readonly isLoading: boolean;
}

/**
 * The learner's next action, resolved across every enrolled course.
 *
 * The previous dashboard read the spine for ONE course, chosen as "the most
 * recently updated course you can see". That is a heuristic, not an answer: a
 * student with a checkpoint due in an hour in course B would see nothing if
 * course A happened to be edited more recently. The handoff asks Home to
 * resolve "one recoverable next action", which only means something if the
 * candidate set is every course.
 *
 * So this fans the checklist out per course (reusing `workItemKeys.checklist`,
 * so it shares the cache with any per-course read) and resolves once.
 */
export function useLearningPath(now: Date): LearningPathResult {
  const t = useTranslations("student.home");
  const { getToken, isSignedIn } = useAuth();
  const { data: courses, isLoading: coursesLoading } = useCourses();

  const courseList = useMemo(() => courses ?? [], [courses]);
  const enabled = isSignedIn === true && courseList.length > 0;

  const queries = useQueries({
    queries: courseList.map((course) => ({
      queryKey: workItemKeys.checklist(course.id),
      queryFn: async () => {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const response = await apiFetch<ApiEnvelope<readonly ChecklistItem[]>>(
          `/courses/${course.id}/checklist`,
          { token }
        );
        return response.data;
      },
      enabled,
      staleTime: 30_000,
      retry: (count: number, error: unknown) =>
        !isAuthError(error) && count < 2,
    })),
  });

  // Stable signature so the memo recomputes only when the fanned-out data does.
  const signature = queries
    .map((query) => (query.data ? query.data.length : -1))
    .join(",");

  const isLoading =
    coursesLoading || (enabled && queries.some((query) => query.isLoading));

  const all = useMemo<readonly LearningAction[]>(() => {
    const copy = {
      scheduled: (at: string) =>
        t("opensOn", { date: formatDay(at) }),
      closed: (at: string) => t("closedOn", { date: formatDay(at) }),
      locked: t("lockedGeneric"),
    };

    const actions: LearningAction[] = [];
    queries.forEach((query, index) => {
      const course = courseList[index];
      if (!course || !query.data) return;
      actions.push(
        ...buildActions(
          {
            id: course.id,
            code: course.code ?? course.name,
            name: course.name,
          },
          query.data,
          now,
          copy
        )
      );
    });
    return actions;
    // `signature` captures the meaningful change in the fanned-out query data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseList, signature, now, t]);

  const day = useMemo(() => resolveLearningDay(all), [all]);

  return { ...day, all, isLoading };
}

/** "Fri, 26 Jun" for a reason sentence. Locale comes from the caller's page. */
function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
