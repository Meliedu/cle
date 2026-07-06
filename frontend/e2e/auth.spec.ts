import { test, expect } from '@playwright/test';

/**
 * Auth-related E2E smoke tests.
 *
 * These verify public page rendering and unauthenticated redirect behavior
 * against the current Better Auth sign-in/sign-up screens (the app migrated
 * off Clerk). Authenticated flows require a live backend session (Better Auth
 * issues JWTs server-side and role gating runs in `proxy.ts`), which this
 * harness's webServer (frontend `npm run dev` only) cannot provide — so
 * role-routing behavior is covered by the vitest unit tests
 * (`src/components/layout/role-gate.test.tsx`,
 * `src/app/dashboard/dashboard-redirect.test.tsx`).
 */

test.describe('Landing page', () => {
  test('renders with Sign In and Get Started links', async ({ page }) => {
    await page.goto('/');

    const signInLink = page.getByRole('link', { name: 'Sign In' }).first();
    const getStartedLink = page.getByRole('link', { name: 'Get Started' });

    await expect(signInLink).toBeVisible();
    await expect(getStartedLink).toBeVisible();
  });

  test('displays the hero heading', async ({ page }) => {
    await page.goto('/');

    const heading = page.getByRole('heading', { level: 1 });
    await expect(heading).toBeVisible();
    await expect(heading).toContainText('Learn languages smarter');
  });

  test('displays feature cards', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Smart Quizzes')).toBeVisible();
    await expect(page.getByText('AI Flashcards')).toBeVisible();
    await expect(page.getByText('Pronunciation Practice')).toBeVisible();
    await expect(page.getByText('Multilingual Support')).toBeVisible();
  });
});

test.describe('Unauthenticated redirect', () => {
  test('visiting /dashboard redirects to sign-in', async ({ page }) => {
    // `proxy.ts` runs a Better Auth session check; an unauthenticated request
    // to a protected route is redirected to /sign-in.
    await page.goto('/dashboard');

    await page.waitForURL(/sign-in/, { timeout: 10_000 });
    expect(page.url()).toContain('sign-in');
  });
});

test.describe('Sign-in page', () => {
  test('renders the Better Auth sign-in form', async ({ page }) => {
    await page.goto('/sign-in');

    // Heading + email/password fields + the footer link to sign-up.
    await expect(
      page.getByRole('heading', { name: 'Sign in to Meli' })
    ).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Sign in' })
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Forgot password?' })
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Create an account' })
    ).toBeVisible();
  });
});

test.describe('Sign-up page', () => {
  test('renders the Better Auth sign-up form', async ({ page }) => {
    await page.goto('/sign-up');

    await expect(
      page.getByRole('heading', { name: 'Join the studio' })
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Sign in' })
    ).toBeVisible();
  });
});
