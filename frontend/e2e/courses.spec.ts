import { test, expect } from '@playwright/test';

/**
 * Course-related E2E smoke tests.
 *
 * The /dashboard/* routes are protected by Clerk middleware, so these
 * tests will be redirected to /sign-in when run without authentication.
 *
 * To run authenticated tests:
 * 1. Configure Clerk Testing Tokens or a Clerk test instance
 *    (https://clerk.com/docs/testing/overview)
 * 2. Use `page.context().addCookies(...)` or Playwright's storageState
 *    to inject a valid session before navigating to protected routes.
 *
 * The tests below are structured so they can be enabled once auth is
 * configured. For now, the redirect-to-sign-in behavior is verified
 * in auth.spec.ts. We include additional structural tests that verify
 * the public landing page course-related CTAs.
 */

test.describe('Landing page course CTAs', () => {
  test('"Start Learning" links to sign-up', async ({ page }) => {
    await page.goto('/');

    const startLearningLink = page.getByRole('link', { name: 'Start Learning' });
    await expect(startLearningLink).toBeVisible();
    await expect(startLearningLink).toHaveAttribute('href', '/sign-up');
  });
});

test.describe('Courses page (requires auth)', () => {
  // These tests document the expected behavior behind authentication.
  // They will currently redirect to sign-in because no auth session
  // is injected. Mark them as fixme until Clerk testing tokens are set up.

  test.fixme('course list page shows Create Course button', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses');

    const heading = page.getByRole('heading', { name: 'Courses' });
    await expect(heading).toBeVisible();

    const createButton = page.getByRole('button', { name: 'Create Course' });
    await expect(createButton).toBeVisible();
  });

  test.fixme('Create Course dialog opens when button is clicked', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses');

    const createButton = page.getByRole('button', { name: 'Create Course' });
    await createButton.click();

    // The dialog should appear with the "Create Course" title and form fields
    const dialogTitle = page.getByRole('heading', { name: 'Create Course' });
    await expect(dialogTitle).toBeVisible();

    // Verify the form fields are present
    await expect(page.getByLabel(/Course Name/)).toBeVisible();
    await expect(page.getByLabel(/Course Code/)).toBeVisible();
    await expect(page.getByLabel(/Semester/)).toBeVisible();
  });

  test.fixme('Create Course dialog validates required fields', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses');

    const createButton = page.getByRole('button', { name: 'Create Course' });
    await createButton.click();

    // Submit the empty form
    const submitButton = page.getByRole('button', { name: 'Create Course' }).last();
    await submitButton.click();

    // Validation errors should appear for required fields
    await expect(page.getByText('Course name is required')).toBeVisible();
    await expect(page.getByText('Course code is required')).toBeVisible();
    await expect(page.getByText('Semester is required')).toBeVisible();
  });

  test.fixme('course search filters the list', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses');

    const searchInput = page.getByPlaceholder('Search courses...');
    await expect(searchInput).toBeVisible();

    // Type a search query that should filter results
    await searchInput.fill('Chinese');

    // "Chinese for Beginners" should remain visible
    await expect(page.getByText('Chinese for Beginners')).toBeVisible();

    // Other courses should not be visible
    await expect(page.getByText('Academic English Writing')).not.toBeVisible();
  });
});
