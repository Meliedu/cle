import { test, expect } from '@playwright/test';

/**
 * Auth-related E2E smoke tests.
 *
 * These tests verify public page rendering and unauthenticated redirect
 * behavior. Full sign-in/sign-up flows require Clerk Testing Tokens
 * (https://clerk.com/docs/testing/overview) or a Clerk test instance,
 * which is out of scope for this initial setup.
 */

test.describe('Landing page', () => {
  test('renders with Sign In and Get Started links', async ({ page }) => {
    await page.goto('/');

    // The header should contain navigation links to auth pages
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

    // Verify at least the four feature titles are visible
    await expect(page.getByText('Smart Quizzes')).toBeVisible();
    await expect(page.getByText('AI Flashcards')).toBeVisible();
    await expect(page.getByText('Pronunciation Practice')).toBeVisible();
    await expect(page.getByText('Multilingual Support')).toBeVisible();
  });
});

test.describe('Unauthenticated redirect', () => {
  test('visiting /dashboard redirects to sign-in', async ({ page }) => {
    // Clerk middleware protects /dashboard — an unauthenticated request
    // should be redirected to /sign-in (or a Clerk-hosted sign-in URL).
    await page.goto('/dashboard');

    // Wait for navigation to settle. The URL should contain "sign-in".
    await page.waitForURL(/sign-in/, { timeout: 10_000 });
    expect(page.url()).toContain('sign-in');
  });
});

test.describe('Sign-in page', () => {
  test('renders the Clerk sign-in form container', async ({ page }) => {
    await page.goto('/sign-in');

    // Clerk injects its form into the page. The outer centering wrapper
    // should be present. The Clerk component itself renders inside a
    // shadow DOM or iframe depending on the version, so we check for the
    // page-level wrapper being visible as a smoke test.
    //
    // NOTE: For deeper assertions on Clerk UI elements, configure
    // Clerk Testing Tokens to get a predictable rendered form.
    const wrapper = page.locator('div.flex.min-h-screen');
    await expect(wrapper).toBeVisible();
  });
});

test.describe('Sign-up page', () => {
  test('renders the Clerk sign-up form container', async ({ page }) => {
    await page.goto('/sign-up');

    const wrapper = page.locator('div.flex.min-h-screen');
    await expect(wrapper).toBeVisible();
  });
});
