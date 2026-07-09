import { test, expect } from '@playwright/test';

/**
 * Auth + public-surface E2E smoke tests (infra-free).
 *
 * These verify public page rendering and unauthenticated redirect behavior
 * against the CURRENT CLE "Checkpoint Loop" UI (the app was rebuilt off the old
 * RAG product and off Clerk — it now runs Better Auth + role-scoped route
 * trees). Assertions target what `src/app/page.tsx`,
 * `src/app/sign-in/[[...sign-in]]/page.tsx`, and
 * `src/app/sign-up/[[...sign-up]]/page.tsx` actually render today.
 *
 * No backend is required: these only touch the public landing/auth screens and
 * the `proxy.ts` session gate (unauthenticated → /sign-in). Authenticated role
 * routing is covered by the live-stack demo-flow.spec.ts (MELI_LIVE_STACK=1) and
 * by the vitest unit tests.
 */

test.describe('Landing page', () => {
  test('renders the header Sign in / Get started CTAs', async ({ page }) => {
    await page.goto('/');

    // Header nav links (case-sensitive current copy).
    await expect(
      page.getByRole('link', { name: 'Sign in' }).first()
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Get started' }).first()
    ).toBeVisible();
  });

  test('displays the hero heading and product framing', async ({ page }) => {
    await page.goto('/');

    const heading = page.getByRole('heading', { level: 1 });
    await expect(heading).toBeVisible();
    await expect(heading).toContainText('reviewed learning habit');

    // The CLE HKUST pilot eyebrow + checkpoint framing in the hero copy.
    await expect(
      page.getByText(/HKUST Centre for Language Education/i).first()
    ).toBeVisible();
    await expect(
      page.getByText(/checkpoint-centred course loop/i)
    ).toBeVisible();
  });

  test('displays the course operating loop stages', async ({ page }) => {
    await page.goto('/');

    // The six-stage loop section + a few of its stage titles.
    await expect(
      page.getByRole('heading', { name: 'The course operating loop' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Course context' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Checkpoint planning' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Course memory' })
    ).toBeVisible();
  });

  test('"Get started" CTA links to sign-up', async ({ page }) => {
    await page.goto('/');

    const getStarted = page
      .getByRole('link', { name: 'Get started' })
      .first();
    await expect(getStarted).toHaveAttribute('href', '/sign-up');
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

    await expect(
      page.getByRole('heading', { name: 'Sign in to Meli' })
    ).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Email' })).toBeVisible();
    await expect(
      page.getByRole('textbox', { name: 'Password' })
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
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
      page.getByRole('heading', { name: 'Create your account' })
    ).toBeVisible();
    await expect(
      page.getByRole('textbox', { name: 'Full name' })
    ).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Email' })).toBeVisible();
    await expect(
      page.getByRole('textbox', { name: 'Password' })
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Create account' })
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Sign in' })).toBeVisible();
  });
});
