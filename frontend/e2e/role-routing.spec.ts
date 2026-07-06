import { test, expect } from '@playwright/test';

/**
 * Role-routing E2E.
 *
 * Only an honest, infra-free assertion lives here: the role-scoped route trees
 * (`/teacher/*`, `/student/*`) exist and are session-gated by `proxy.ts`, so an
 * unauthenticated visit redirects to /sign-in.
 *
 * Authenticated role routing (instructor → /teacher/dashboard, student →
 * /student/dashboard, wrong-lane redirect via RoleGate) CANNOT be exercised
 * here: Better Auth issues its session/JWT server-side and role gating runs in
 * `proxy.ts` (server, not the browser), so Playwright `page.route` mocking
 * cannot fake an authenticated session, and this harness's webServer starts the
 * frontend only (no backend to answer `/api/auth/me`). That behavior is covered
 * deterministically by the vitest unit tests:
 *   - src/components/layout/role-gate.test.tsx
 *   - src/app/dashboard/dashboard-redirect.test.tsx
 */

test.describe('Role-scoped routes are session-gated', () => {
  for (const path of ['/teacher/dashboard', '/student/dashboard']) {
    test(`unauthenticated ${path} redirects to sign-in`, async ({ page }) => {
      await page.goto(path);

      await page.waitForURL(/sign-in/, { timeout: 10_000 });
      expect(page.url()).toContain('sign-in');
    });
  }
});
