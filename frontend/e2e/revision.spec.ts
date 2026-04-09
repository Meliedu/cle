import { test, expect } from '@playwright/test';

/**
 * Revision Practice E2E smoke tests.
 *
 * The revision page lives at /dashboard/courses/[courseId]/revision,
 * which requires authentication. These tests document the expected
 * behavior of the full revision flow and are marked fixme until Clerk
 * testing tokens are configured.
 *
 * To enable:
 * 1. Set up Clerk Testing Tokens
 *    (https://clerk.com/docs/testing/overview)
 * 2. Inject an authenticated session via storageState or cookies
 * 3. Replace TEST_COURSE_ID with a seeded course that has pool items
 * 4. Remove the test.fixme() wrappers
 */

const TEST_COURSE_ID = 'TEST_COURSE_ID';

test.describe('Revision Practice (requires auth)', () => {
  test.fixme(
    'renders the content type picker on the revision page',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // The page heading should be visible
      const heading = page.getByRole('heading', { name: 'Revision Practice' });
      await expect(heading).toBeVisible();

      // The content type picker should display all three practice options
      await expect(page.getByText('Choose Your Practice')).toBeVisible();
      await expect(
        page.getByRole('button', { name: /Start Quiz practice/i }),
      ).toBeVisible();
      await expect(
        page.getByRole('button', { name: /Start Flashcard practice/i }),
      ).toBeVisible();
      await expect(
        page.getByRole('button', { name: /Start Speaking practice/i }),
      ).toBeVisible();
    },
  );

  test.fixme(
    'student can start a quiz session and see a question',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      // Requires a seeded course with quiz pool items
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // Select quiz practice
      await page
        .getByRole('button', { name: /Start Quiz practice/i })
        .click();

      // Should see either a loading state or a question appear
      await expect(
        page.locator('[data-testid="question-text"]'),
      ).toBeVisible({ timeout: 15_000 });
    },
  );

  test.fixme(
    'student can answer a quiz question and see feedback',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      // Requires a seeded course with quiz pool items
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // Start a quiz session
      await page
        .getByRole('button', { name: /Start Quiz practice/i })
        .click();

      // Wait for the question to appear
      await expect(
        page.locator('[data-testid="question-text"]'),
      ).toBeVisible({ timeout: 15_000 });

      // Click the first answer option (A, B, C, or D)
      await page.getByRole('button', { name: /^[A-D]/ }).first().click();

      // Feedback should appear after answering
      await expect(
        page.locator('[data-testid="item-feedback"]'),
      ).toBeVisible();
    },
  );

  test.fixme(
    'student can complete a quiz session and see the summary',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      // Requires a seeded course with quiz pool items
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // Start a quiz session
      await page
        .getByRole('button', { name: /Start Quiz practice/i })
        .click();

      // Wait for the first question
      await expect(
        page.locator('[data-testid="question-text"]'),
      ).toBeVisible({ timeout: 15_000 });

      // Answer the question
      await page.getByRole('button', { name: /^[A-D]/ }).first().click();

      // Feedback should appear
      await expect(
        page.locator('[data-testid="item-feedback"]'),
      ).toBeVisible();

      // End the session
      await page.getByRole('button', { name: /End Session/i }).click();

      // The session summary should appear with the score gauge and stats
      await expect(
        page.locator('[data-testid="session-summary"]'),
      ).toBeVisible();
      await expect(page.getByText('Session Complete!')).toBeVisible();
      await expect(page.getByText('Average Score')).toBeVisible();
      await expect(page.getByText('Items')).toBeVisible();
      await expect(page.getByText('Duration')).toBeVisible();
    },
  );

  test.fixme(
    'student can start a flashcard session',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      // Requires a seeded course with flashcard pool items
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // Select flashcard practice
      await page
        .getByRole('button', { name: /Start Flashcard practice/i })
        .click();

      // Should see the flashcard content loading or displayed
      // (Flashcard items don't use data-testid="question-text", but the
      // player component should render something in the playing state)
      await expect(
        page.locator('[data-testid="question-text"], [data-testid="flashcard-front"]'),
      ).toBeVisible({ timeout: 15_000 });
    },
  );

  test.fixme(
    'session summary shows Practice Again button that reloads the page',
    async ({ page }) => {
      // AUTH REQUIRED: Inject Clerk session before navigating
      // Requires a seeded course with pool items
      await page.goto(`/dashboard/courses/${TEST_COURSE_ID}/revision`);

      // Start and immediately end a session to reach the summary
      await page
        .getByRole('button', { name: /Start Quiz practice/i })
        .click();

      await expect(
        page.locator('[data-testid="question-text"]'),
      ).toBeVisible({ timeout: 15_000 });

      // Answer one question then end
      await page.getByRole('button', { name: /^[A-D]/ }).first().click();
      await page.getByRole('button', { name: /End Session/i }).click();

      await expect(
        page.locator('[data-testid="session-summary"]'),
      ).toBeVisible();

      // The "Practice Again" button should be visible
      await expect(
        page.getByRole('button', { name: /Practice Again/i }),
      ).toBeVisible();
    },
  );
});
