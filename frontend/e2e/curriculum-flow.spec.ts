import { test, expect } from '@playwright/test';

/**
 * Curriculum flow E2E smoke tests.
 *
 * Part A (live) — Unauthenticated route protection
 * ──────────────────────────────────────────────────
 * Verifies that each new curriculum route (modules, meetings, objectives,
 * assignments, syllabus) redirects unauthenticated visitors to /sign-in.
 * These tests run against the live dev server and require no auth setup.
 *
 * Part B (fixme) — Full instructor + student curriculum flow
 * ──────────────────────────────────────────────────────────
 * Full smoke test covering:
 *   Instructor: create module → create meeting → create assignment (published)
 *   Student:    see items on calendar, open assignment, submit answer
 *
 * To un-fixme Part B, complete the following auth scaffolding:
 *   1. Add a Better Auth test-session setup project in playwright.config.ts
 *      that logs in via the Better Auth email/password flow (POST to
 *      /api/auth/sign-in/email) and writes two storageState files:
 *        - e2e/.auth/instructor.json  (ust.hk email)
 *        - e2e/.auth/student.json     (connect.ust.hk email)
 *   2. Use `test.use({ storageState: 'e2e/.auth/instructor.json' })` for the
 *      instructor context and pass `storageState: 'e2e/.auth/student.json'`
 *      to `browser.newContext()` for the student context.
 *   3. Replace the `<course-id>` placeholders below with a real UUID created
 *      by the test setup (or seed a fixed UUID via `seed.py`).
 *   4. Remove the `test.fixme(true, ...)` guard in the describe block.
 */

// ─── Part A: unauthenticated route protection ───────────────────────────────

test.describe('Curriculum routes — unauthenticated', () => {
  // Placeholder UUID used in every guarded route.
  // The test is about the redirect, not the resource existing.
  const PLACEHOLDER_COURSE_ID = '00000000-0000-0000-0000-000000000000';

  const guardedRoutes = [
    `/dashboard/courses/${PLACEHOLDER_COURSE_ID}/modules`,
    `/dashboard/courses/${PLACEHOLDER_COURSE_ID}/meetings`,
    `/dashboard/courses/${PLACEHOLDER_COURSE_ID}/objectives`,
    `/dashboard/courses/${PLACEHOLDER_COURSE_ID}/assignments`,
    `/dashboard/courses/${PLACEHOLDER_COURSE_ID}/syllabus`,
  ];

  for (const route of guardedRoutes) {
    test(`${route} redirects to sign-in`, async ({ page }) => {
      await page.goto(route);
      await page.waitForURL(/sign-in/, { timeout: 10_000 });
      await expect(page).toHaveURL(/sign-in/);
    });
  }
});

// ─── Part B: full instructor + student flow (requires auth fixture) ──────────

test.describe('Curriculum end-to-end flow', () => {
  test.fixme(
    true,
    'Requires Better Auth test session storage state — enable when auth fixture is wired (see top-of-file JSDoc for steps)',
  );

  // Placeholder — replace with a real course UUID created by test setup.
  const COURSE_ID = '<course-id>';

  test(
    'instructor creates module → meeting → assignment; student submits and sees it on calendar',
    async ({ page, browser }) => {
      // ── Instructor: create a module ──────────────────────────────────────
      await page.goto(`/dashboard/courses/${COURSE_ID}/modules`);
      await page.getByRole('button', { name: /add module/i }).click();
      await page.getByLabel(/name/i).fill('Week 1');
      await page.getByLabel(/order/i).fill('1');
      await page.getByRole('button', { name: /save|create/i }).click();
      await expect(page.getByText('Week 1')).toBeVisible();

      // ── Instructor: create a meeting ─────────────────────────────────────
      await page.goto(`/dashboard/courses/${COURSE_ID}/meetings`);
      await page.getByRole('button', { name: /add meeting/i }).click();
      await page.getByLabel(/index/i).fill('1');
      await page.getByLabel(/scheduled/i).fill('2026-09-01T10:00');
      await page.getByLabel(/title/i).fill('Lecture 1');
      await page.getByRole('button', { name: /save|create/i }).click();
      await expect(page.getByText('Lecture 1')).toBeVisible();

      // ── Instructor: create a published assignment ─────────────────────────
      await page.goto(`/dashboard/courses/${COURSE_ID}/assignments`);
      await page.getByRole('button', { name: /add assignment/i }).click();
      await page.getByLabel(/title/i).fill('Essay 1');
      await page.getByLabel(/due/i).fill('2026-09-15T23:59');
      await page.locator('input[type="checkbox"][name="is_published"]').check();
      await page.getByRole('button', { name: /save|create/i }).click();
      await expect(page.getByText('Essay 1')).toBeVisible();

      // ── Student: view calendar, confirm items appear ──────────────────────
      // Student auth context — swap storageState once the fixture exists.
      const studentCtx = await browser.newContext(
        /* { storageState: 'e2e/.auth/student.json' } */
      );
      const studentPage = await studentCtx.newPage();

      await studentPage.goto('/dashboard/calendar');
      await expect(studentPage.getByText(/lecture 1/i)).toBeVisible();
      await expect(studentPage.getByText(/essay 1/i)).toBeVisible();

      // ── Student: open assignment and submit ───────────────────────────────
      await studentPage.goto(`/dashboard/courses/${COURSE_ID}/assignments`);
      await studentPage.getByText('Essay 1').click();
      await studentPage.getByRole('textbox').fill('My answer.');
      await studentPage.getByRole('button', { name: /submit/i }).click();
      await expect(studentPage.getByText(/saved/i)).toBeVisible();

      await studentCtx.close();
    },
  );
});
