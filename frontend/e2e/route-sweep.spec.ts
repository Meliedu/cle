import { test, expect } from "@playwright/test";
import {
  seed,
  signInAs,
  expectNoAppError,
  watchForProblems,
  summarizeProblems,
  hasProblems,
  VISIBLE_TIMEOUT,
} from "./fixtures/seed";

/**
 * Exhaustive route sweep against a LIVE stack.
 *
 * Every authenticated route in both lanes is visited and held to four rules:
 *   1. no uncaught exception / error boundary,
 *   2. no console error,
 *   3. no failed network request and no 4xx/5xx API response,
 *   4. a level-1 heading renders (the page committed to *something*: a real
 *      empty state counts, a blank screen does not).
 *
 * Rule 3 is the one that earns its keep: a route can look correct while its
 * data call 500s behind a silent catch, and no "is the heading visible" test
 * will ever notice.
 *
 * Requires MELI_LIVE_STACK=1 plus the seeded demo dataset (see fixtures/seed.ts).
 */

const LIVE = process.env.MELI_LIVE_STACK === "1";

interface Route {
  path: string;
  name: string;
  /** Routes whose h1 is legitimately absent (standalone//full-bleed screens). */
  skipHeading?: boolean;
}

function teacherRoutes(): Route[] {
  const m = seed();
  const c = m.publishedCourseId;
  const draft = m.draftCourseId;
  return [
    { path: "/teacher/dashboard", name: "dashboard" },
    { path: "/teacher/courses", name: "courses list" },
    { path: "/teacher/courses/new", name: "new course" },
    { path: "/teacher/calendar", name: "calendar" },
    { path: "/teacher/insights", name: "insights (global)" },
    { path: "/teacher/notifications", name: "notifications" },
    { path: "/teacher/profile", name: "profile" },
    { path: "/teacher/placement", name: "placement queue" },
    { path: `/teacher/courses/${c}`, name: "course overview" },
    { path: `/teacher/courses/${c}/setup`, name: "course setup" },
    { path: `/teacher/courses/${c}/materials`, name: "materials" },
    { path: `/teacher/courses/${c}/schedule`, name: "schedule" },
    { path: `/teacher/courses/${c}/sessions`, name: "sessions" },
    { path: `/teacher/courses/${c}/sessions/history`, name: "session history" },
    { path: `/teacher/courses/${c}/students`, name: "students" },
    { path: `/teacher/courses/${c}/enrollment`, name: "enrollment" },
    { path: `/teacher/courses/${c}/quiz`, name: "quiz list" },
    { path: `/teacher/courses/${c}/quiz/${m.gradedQuizId}`, name: "quiz detail" },
    {
      path: `/teacher/courses/${c}/quiz/${m.gradedQuizId}/results`,
      name: "quiz results",
    },
    { path: `/teacher/courses/${c}/practice`, name: "practice list" },
    {
      path: `/teacher/courses/${c}/practice/${m.practiceQuizId}`,
      name: "practice detail",
    },
    {
      path: `/teacher/courses/${c}/practice/${m.practiceQuizId}/results`,
      name: "practice results",
    },
    { path: `/teacher/courses/${c}/activities`, name: "activities" },
    { path: `/teacher/courses/${c}/reports`, name: "reports" },
    { path: `/teacher/courses/${c}/insights`, name: "course insights" },
    { path: `/teacher/courses/${c}/memory`, name: "course memory" },
    { path: `/teacher/courses/${draft}`, name: "draft course overview" },
    { path: `/teacher/courses/${draft}/setup`, name: "draft course setup" },
  ];
}

function studentRoutes(): Route[] {
  const m = seed();
  const c = m.publishedCourseId;
  return [
    { path: "/student/dashboard", name: "dashboard" },
    { path: "/student/courses", name: "courses list" },
    { path: "/student/calendar", name: "calendar" },
    { path: "/student/progress", name: "progress" },
    { path: "/student/notifications", name: "notifications" },
    { path: "/student/profile", name: "profile" },
    { path: "/student/join", name: "join a course" },
    { path: "/student/placement", name: "placement" },
    { path: `/student/courses/${c}`, name: "course overview" },
    { path: `/student/courses/${c}/checklist`, name: "checklist" },
    { path: `/student/courses/${c}/schedule`, name: "schedule" },
    { path: `/student/courses/${c}/sessions`, name: "sessions" },
    { path: `/student/courses/${c}/materials`, name: "materials" },
    { path: `/student/courses/${c}/checkpoints`, name: "checkpoints", skipHeading: true },
    { path: `/student/courses/${c}/activities`, name: "activities" },
    {
      path: `/student/courses/${c}/activities/${m.activityId}`,
      name: "activity detail",
    },
    { path: `/student/courses/${c}/quiz/${m.gradedQuizId}`, name: "graded quiz landing" },
    {
      path: `/student/courses/${c}/practice/${m.practiceQuizId}`,
      name: "practice landing",
    },
    { path: `/student/courses/${c}/scores`, name: "scores" },
    { path: `/student/courses/${c}/reports`, name: "reports" },
    { path: `/student/courses/${c}/insights`, name: "insights" },
    { path: `/student/courses/${c}/profile`, name: "learning profile" },
  ];
}

test.describe("route sweep: teacher lane", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");

  for (const route of teacherRoutes()) {
    test(`teacher: ${route.name} (${route.path})`, async ({ page }) => {
      const problems = watchForProblems(page);
      await signInAs(page, "teacher");
      await page.goto(route.path);

      await expectNoAppError(page);
      if (!route.skipHeading) {
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
          timeout: VISIBLE_TIMEOUT,
        });
      }
      // Let in-flight data calls settle so their failures are recorded.
      await page.waitForLoadState("networkidle").catch(() => {});
      expect(
        hasProblems(problems),
        `${route.path}\n${summarizeProblems(problems)}`
      ).toBe(false);
    });
  }
});

test.describe("route sweep: student lane", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");

  for (const route of studentRoutes()) {
    test(`student: ${route.name} (${route.path})`, async ({ page }) => {
      const problems = watchForProblems(page);
      await signInAs(page, "student");
      await page.goto(route.path);

      await expectNoAppError(page);
      if (!route.skipHeading) {
        await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
          timeout: VISIBLE_TIMEOUT,
        });
      }
      await page.waitForLoadState("networkidle").catch(() => {});
      expect(
        hasProblems(problems),
        `${route.path}\n${summarizeProblems(problems)}`
      ).toBe(false);
    });
  }
});
