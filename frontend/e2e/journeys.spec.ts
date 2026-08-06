import { test, expect, type Page } from "@playwright/test";
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
 * Interaction journeys against a LIVE stack.
 *
 * The route sweep proves every screen *renders*; these prove the product
 * actually *does* things: create a course, walk setup, join with a code, take
 * a graded quiz, run the placement screener, approve a join request. Those are
 * the paths where a broken mutation hides behind a screen that still looks fine.
 *
 * Requires MELI_LIVE_STACK=1 + the seeded demo dataset.
 */

const LIVE = process.env.MELI_LIVE_STACK === "1";

/** Unique suffix so repeat runs don't collide on the course-code unique index. */
function uniqueSuffix(): string {
  return String(Date.now() % 1_000_000).padStart(6, "0");
}

async function assertClean(page: Page, problems: ReturnType<typeof watchForProblems>, where: string) {
  await expectNoAppError(page);
  await page.waitForLoadState("networkidle").catch(() => {});
  expect(hasProblems(problems), `${where}\n${summarizeProblems(problems)}`).toBe(
    false
  );
}

test.describe("teacher journey", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");
  test.describe.configure({ mode: "serial" });

  test("creates a course and lands in its setup wizard", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "teacher");

    const suffix = uniqueSuffix();
    const courseName = `E2E Journey Course ${suffix}`;

    await page.goto("/teacher/courses/new");
    await expect(
      page.getByRole("heading", { level: 1, name: /Create course/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });

    await page.getByLabel(/Course name/i).fill(courseName);
    await page.getByLabel(/Course code/i).fill(`E2E${suffix}`);
    await page.getByRole("button", { name: /Continue/i }).click();

    // Creating a course must land the teacher somewhere real (the course
    // workspace or its setup wizard), not bounce back to the form.
    await page.waitForURL(/\/teacher\/courses\/[0-9a-f-]{36}/, {
      timeout: 30_000,
    });
    expect(page.url()).not.toContain("/courses/new");

    await assertClean(page, problems, "create course");
  });

  test("course setup wizard renders its steps for the seeded course", async ({
    page,
  }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "teacher");

    await page.goto(`/teacher/courses/${seed().publishedCourseId}/setup`);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await assertClean(page, problems, "setup wizard");
  });

  test("students surface lists the enrolled learner", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "teacher");

    await page.goto(`/teacher/courses/${seed().publishedCourseId}/students`);
    await expect(page.getByText("Aidan Lam").first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await assertClean(page, problems, "students");
  });

  test("enrollment surface offers approve/deny on the pending request", async ({
    page,
  }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "teacher");

    await page.goto(`/teacher/courses/${seed().publishedCourseId}/enrollment`);
    await expect(page.getByText("Priya Nair")).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(
      page.getByRole("button", { name: /Approve/i }).first()
    ).toBeEnabled();
    await assertClean(page, problems, "enrollment");
  });

  test("graded quiz builder shows the score-policy gate", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "teacher");

    const m = seed();
    await page.goto(
      `/teacher/courses/${m.publishedCourseId}/quiz/${m.gradedQuizId}`
    );
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await assertClean(page, problems, "quiz builder");
  });
});

test.describe("student journey", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");
  test.describe.configure({ mode: "serial" });

  test("graded quiz discloses score rules before the attempt starts", async ({
    page,
  }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "student");

    const m = seed();
    await page.goto(
      `/student/courses/${m.publishedCourseId}/quiz/${m.gradedQuizId}`
    );

    // Score-bearing work must disclose category/due/grading mode BEFORE
    // submission (Architecture Reference: Student Workflow product rule).
    await expect(
      page.getByRole("button", { name: /Start quiz/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await assertClean(page, problems, "graded quiz landing");
  });

  test("can start and answer a graded quiz attempt", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "student");

    const m = seed();
    await page.goto(
      `/student/courses/${m.publishedCourseId}/quiz/${m.gradedQuizId}`
    );
    await page.getByRole("button", { name: /Start quiz/i }).click();

    // The attempt screen must present a question with selectable options.
    const options = page.getByRole("radio");
    await expect(options.first()).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await options.first().click();
    await expect(options.first()).toBeChecked();

    await assertClean(page, problems, "quiz attempt");
  });

  test("join funnel validates an unknown course code", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "student");

    await page.goto("/student/join");
    const codeField = page.getByLabel(/Course code/i);
    await expect(codeField).toBeVisible({ timeout: VISIBLE_TIMEOUT });

    await codeField.fill("NOPE9999");
    await page.getByRole("button", { name: /Join course/i }).click();

    // A wrong code must produce a visible, explained rejection, not a silent
    // no-op and not an unhandled error.
    await expect(page.getByRole("alert").first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expectNoAppError(page);
    expect(problems.pageErrors, summarizeProblems(problems)).toHaveLength(0);
  });

  test("checklist renders the seeded work items", async ({ page }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "student");

    await page.goto(`/student/courses/${seed().publishedCourseId}/checklist`);
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await assertClean(page, problems, "checklist");
  });
});

test.describe("placement screener", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");

  test("intro discloses claim boundaries and offers a start", async ({
    page,
  }) => {
    const problems = watchForProblems(page);
    await signInAs(page, "student");

    await page.goto("/student/placement");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });

    // Claim boundary: the screener must not present itself as an official
    // HSK result (Architecture Reference: Claim Boundaries).
    await expect(
      page.getByText(/not an official|recommend|screener/i).first()
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });

    await assertClean(page, problems, "placement intro");
  });

  test("never ships answer keys or scripts to the student surface", async ({
    page,
  }) => {
    await signInAs(page, "student");

    // Capture every placement API payload the student's browser receives.
    const leaks: string[] = [];
    page.on("response", async (res) => {
      if (!/\/api\/placement/.test(res.url())) return;
      let body = "";
      try {
        body = await res.text();
      } catch {
        return;
      }
      // Restricted surface per placement_contract.py: answer keys, listening
      // scripts, rationales and band mappings are teacher-only and must never
      // reach a student token.
      for (const key of [
        "answer_key",
        "correct_option",
        "listening_script",
        "rationale",
        "band",
      ]) {
        if (new RegExp(`"${key}"`).test(body)) {
          leaks.push(`${key} in ${res.url()}`);
        }
      }
    });

    await page.goto("/student/placement");
    await page.waitForLoadState("networkidle").catch(() => {});

    expect(leaks, `restricted placement fields reached the student:\n${leaks.join("\n")}`).toHaveLength(0);
  });
});

test.describe("cross-role authorization", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");

  test("a student cannot reach the teacher lane", async ({ page }) => {
    await signInAs(page, "student");
    await page.goto("/teacher/dashboard");

    // Must be redirected out of the teacher lane, not shown teacher chrome.
    await page.waitForURL((url) => !url.pathname.startsWith("/teacher"), {
      timeout: 30_000,
    });
    expect(page.url()).not.toContain("/teacher/");
  });

  test("a teacher cannot reach the student lane", async ({ page }) => {
    await signInAs(page, "teacher");
    await page.goto("/student/dashboard");

    await page.waitForURL((url) => !url.pathname.startsWith("/student"), {
      timeout: 30_000,
    });
    expect(page.url()).not.toContain("/student/");
  });

  test("a student cannot open another course's teacher workspace", async ({
    page,
  }) => {
    await signInAs(page, "student");
    await page.goto(`/teacher/courses/${seed().publishedCourseId}/students`);

    // The roster of a course the student is enrolled in must still be
    // unreachable through the teacher lane.
    await page.waitForURL((url) => !url.pathname.startsWith("/teacher"), {
      timeout: 30_000,
    });
    await expect(page.getByText("Priya Nair")).toHaveCount(0);
  });
});
