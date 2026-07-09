import { test, expect, type Page } from "@playwright/test";

/**
 * End-to-end walk of the CLE "Checkpoint Loop" flow against a LIVE stack
 * (backend + Postgres + Better Auth) seeded with the demo dataset:
 *   backend/seed_demo_content.py  +  frontend/scripts/seed-auth.mjs
 *
 * Gated on MELI_LIVE_STACK=1 because the default e2e webServer runs the
 * frontend only (no backend), and CI has no database — matching the P0 handoff
 * decision to keep authenticated e2e out of the infra-free suite. Run locally
 * (Git Bash: prefix env with MSYS_NO_PATHCONV=1):
 *   MELI_LIVE_STACK=1 npx playwright test e2e/demo-flow.spec.ts
 *
 * The suite walks BOTH lanes comprehensively via direct route navigation with
 * the known seeded course id — direct nav is more resilient than click-through
 * and lets each area be asserted on stable shell text (course-name PageHeader,
 * active tab label) rather than brittle DOM. Content bodies are backend/seed
 * dependent, so per-area assertions target the workspace chrome that is
 * guaranteed to render for an authenticated, enrolled/owning user.
 */
const LIVE = process.env.MELI_LIVE_STACK === "1";
const PASSWORD = "MeliDemo2026!";

const TEACHER_EMAIL = "meli.teacher@ust.hk";
const STUDENT_EMAIL = "meli.student@connect.ust.hk";

// Seeded LANG1511 course + a published graded quiz on it.
const COURSE_ID = "86f54703-54df-43ba-ac72-fcdc9db9e4d5";
const GRADED_QUIZ_ID = "44bfab0b-42ea-468c-9df5-dcf851bc382d";
const COURSE_NAME = /Chinese I for Non-Chinese Speakers/i;

const NAV_TIMEOUT = 45_000;
const VISIBLE_TIMEOUT = 20_000;

async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/sign-in");
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', PASSWORD);
  await page.click('button[type="submit"]');
}

/**
 * Sign in and wait for the role-scoped dashboard. After Better Auth issues the
 * session the sign-in page pushes `/dashboard`, which client-resolves the role
 * and replaces with `/{role}/dashboard`. Under parallel load against the live
 * backend that hop can be slow, so we wait on the final role URL with a generous
 * timeout rather than the intermediate `/dashboard`.
 */
async function signInAndLand(
  page: Page,
  email: string,
  role: "teacher" | "student"
): Promise<void> {
  await signIn(page, email);
  await page.waitForURL(new RegExp(`/${role}/dashboard`), {
    timeout: NAV_TIMEOUT,
  });
}

/**
 * Assert we landed on a real screen (not a crash / hard error boundary). Screens
 * may legitimately show empty/waiting states — those are fine; only an app-level
 * runtime error is a failure.
 */
async function expectNoAppError(page: Page): Promise<void> {
  await expect(
    page.getByText(/application error|something went wrong/i)
  ).toHaveCount(0);
}

test.describe("demo checkpoint-loop flow (live stack)", () => {
  test.skip(!LIVE, "requires MELI_LIVE_STACK=1 + seeded backend");
  // Each test signs in against the live backend; cap parallelism so the shared
  // dev server + Postgres don't thrash under the full authenticated walk (the
  // login → role-dashboard redirect is the contention-sensitive step).
  test.describe.configure({ mode: "parallel", retries: 1 });

  // ---------------------------------------------------------------- teacher

  test("teacher: dashboard cockpit", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");
    await expect(
      page.getByRole("heading", { name: /Welcome back/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });

  test("teacher: courses list shows the seeded course", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto("/teacher/courses");
    await expect(page.getByText(/LANG1511/).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(page.getByText(COURSE_NAME).first()).toBeVisible();
  });

  test("teacher: course overview workspace", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(`/teacher/courses/${COURSE_ID}`);
    // Shared workspace shell renders the course name as the PageHeader title.
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    // Tab nav is present.
    await expect(
      page.getByRole("link", { name: "Enrollment" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("teacher: sessions (checkpoints) tab", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(`/teacher/courses/${COURSE_ID}/sessions`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    // "Checkpoints" is the sessions tab label; the active tab link is present.
    await expect(
      page.getByRole("link", { name: "Checkpoints" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("teacher: enrollment tab shows the pending join request", async ({
    page,
  }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(`/teacher/courses/${COURSE_ID}/enrollment`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });

    // The seeded pending student (Priya Nair) awaits approval.
    await expect(page.getByText(/awaiting approval/i)).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(page.getByText("Priya Nair")).toBeVisible();
    // Approve/Deny actions render on the request row.
    await expect(
      page.getByRole("button", { name: "Approve" }).first()
    ).toBeVisible();
  });

  test("teacher: activities tab", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(`/teacher/courses/${COURSE_ID}/activities`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(
      page.getByRole("link", { name: "Activities" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("teacher: graded quiz results landing", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(
      `/teacher/courses/${COURSE_ID}/quiz/${GRADED_QUIZ_ID}/results`
    );
    // The teacher results surface is reachable without an app error; body is
    // seed-dependent (may be an empty "no attempts" state), which is fine.
    await expectNoAppError(page);
    await expect(page.locator("body")).toBeVisible();
  });

  test("teacher: reports tab", async ({ page }) => {
    await signInAndLand(page, TEACHER_EMAIL, "teacher");

    await page.goto(`/teacher/courses/${COURSE_ID}/reports`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(
      page.getByRole("link", { name: "Reports" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  // ---------------------------------------------------------------- student

  test("student: dashboard with next-step card", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");
    await expect(
      page.getByRole("heading", { name: /Welcome back, Aidan/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await expectNoAppError(page);
  });

  test("student: courses list shows the enrolled course", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto("/student/courses");
    await expect(page.getByText(COURSE_NAME).first()).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
  });

  test("student: course workspace overview", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    // Student tab nav (checklist / materials) is present.
    await expect(
      page.getByRole("link", { name: "Checklist" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("student: course checklist", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}/checklist`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(
      page.getByRole("link", { name: "Checklist" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("student: checkpoints history", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}/checkpoints`);
    // Standalone (non-shell) page; assert it loads without an app error.
    await expectNoAppError(page);
    await expect(page.locator("body")).toBeVisible();
  });

  test("student: course materials", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}/materials`);
    await expect(page.getByRole("heading", { name: COURSE_NAME })).toBeVisible({
      timeout: VISIBLE_TIMEOUT,
    });
    await expect(
      page.getByRole("link", { name: "Materials" }).first()
    ).toBeVisible();
    await expectNoAppError(page);
  });

  test("student: graded quiz landing shows Start quiz", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(
      `/student/courses/${COURSE_ID}/quiz/${GRADED_QUIZ_ID}`
    );
    // The graded-quiz landing (F8) shows the score-bearing disclosure and an
    // explicit "Start quiz" button before the attempt begins.
    await expect(
      page.getByRole("button", { name: "Start quiz" })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
  });

  test("student: scores & participation record", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}/scores`);
    await expect(
      page.getByRole("heading", { name: /Score & participation record/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await expectNoAppError(page);
  });

  test("student: reports archive", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto(`/student/courses/${COURSE_ID}/reports`);
    await expect(
      page.getByRole("heading", { name: /Your reports/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    await expectNoAppError(page);
  });

  // ---------------------------------------------------------------- join funnel

  test("student: join funnel prompts for a course code", async ({ page }) => {
    await signInAndLand(page, STUDENT_EMAIL, "student");

    await page.goto("/student/join");
    await expect(
      page.getByRole("heading", { name: /Join a course/i })
    ).toBeVisible({ timeout: VISIBLE_TIMEOUT });
    // S003 code-entry field.
    await expect(page.getByLabel(/Course code/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Join course/i })
    ).toBeVisible();
  });
});
