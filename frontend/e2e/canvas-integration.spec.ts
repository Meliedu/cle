import { test, expect, type Page } from '@playwright/test';

/**
 * Canvas integration E2E tests.
 *
 * These cover the two principal happy paths added by the Canvas OAuth
 * integration (Phase 1):
 *
 *   1. Instructor links a Canvas course from the dashboard course picker
 *      -> navigates to the newly created Meli course settings page.
 *   2. Student joins a Meli course from a Canvas enrollment inside the
 *      join-course dialog -> navigates to the Meli course overview.
 *
 * Both flows live behind Clerk-authenticated `/dashboard` routes. Clerk
 * sign-in automation is not yet configured in this repo (see
 * `e2e/courses.spec.ts` for the same pattern: `test.fixme`). The tests
 * below are fully wired up with `page.route` API stubs for the Canvas
 * endpoints, so they can be enabled as soon as Clerk testing tokens
 * (or a `storageState` auth fixture) are introduced — just delete the
 * `test.fixme` and `skip` lines.
 *
 * To enable:
 *   1. Add an auth setup project using Clerk Testing Tokens
 *      (https://clerk.com/docs/testing/overview) that writes a
 *      `storageState` file.
 *   2. Point this test file at that storageState via `test.use`.
 *   3. Remove the `test.fixme(...)` guard below.
 */

const INSTRUCTOR_CANVAS_COURSE = {
  canvas_course_id: 222,
  name: 'CANVAS 101 - Integration Testing',
  course_code: 'CANVAS-101',
  term: 'Spring 2026',
  workflow_state: 'available',
  already_linked_meli_course_id: null as string | null,
};

const STUDENT_CANVAS_COURSE = {
  canvas_course_id: 222,
  name: 'CANVAS 101 - Integration Testing',
  course_code: 'CANVAS-101',
  term: 'Spring 2026',
  workflow_state: 'available',
  already_linked_meli_course_id: 'abc-123',
};

const MELI_COURSE_ID = 'abc-123';

/**
 * Install API stubs for Canvas endpoints hit by the two flows.
 * These match the backend API envelope: {success, data, error}.
 */
async function mockCanvasApis(
  page: Page,
  opts: { role: 'teacher' | 'student' },
): Promise<void> {
  // Canvas connection status - always connected.
  await page.route('**/api/canvas/connection', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          connected: true,
          canvas_user_id: 999,
          scope: 'url:GET|/api/v1/courses',
          linked_at: new Date().toISOString(),
        },
        error: null,
      }),
    });
  });

  // Canvas courses listing, filtered by role.
  await page.route(/\/api\/canvas\/courses(\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    const role = url.searchParams.get('role');
    const payload =
      role === 'teacher'
        ? [INSTRUCTOR_CANVAS_COURSE]
        : [STUDENT_CANVAS_COURSE];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: payload,
        error: null,
      }),
    });
  });

  if (opts.role === 'teacher') {
    // Link endpoint returns a newly-created Meli course id.
    await page.route('**/api/canvas/courses/222/link', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { meli_course_id: MELI_COURSE_ID },
          error: null,
        }),
      });
    });
  } else {
    // Join endpoint returns the linked Meli course id for enrollment.
    await page.route('**/api/canvas/courses/222/join', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { meli_course_id: MELI_COURSE_ID },
          error: null,
        }),
      });
    });
  }

  // Courses list is queried on dashboard mount. Return empty so the
  // "No courses yet" empty state shows and the picker/join dialog are
  // the only things on screen.
  await page.route(/\/api\/courses(\?|$)/, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [],
        error: null,
      }),
    });
  });

  // Swallow the destination course detail fetch after navigation so the
  // test doesn't hang waiting on the real backend.
  await page.route(
    new RegExp(`/api/courses/${MELI_COURSE_ID}($|\\?)`),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            id: MELI_COURSE_ID,
            name: INSTRUCTOR_CANVAS_COURSE.name,
            code: INSTRUCTOR_CANVAS_COURSE.course_code,
            language: 'en',
            semester: INSTRUCTOR_CANVAS_COURSE.term,
            updated_at: new Date().toISOString(),
            created_at: new Date().toISOString(),
          },
          error: null,
        }),
      });
    },
  );
}

test.describe('Canvas integration (authenticated flows)', () => {
  // Clerk auth automation is not yet configured — see header comment.
  // Scaffolding is intentionally complete so these can be flipped on
  // as soon as a storageState fixture exists.
  test.skip(
    true,
    'Clerk auth automation pending; enable once storageState fixture is added',
  );

  test('instructor links a Canvas course from the dashboard picker', async ({
    page,
  }) => {
    await mockCanvasApis(page, { role: 'teacher' });

    await page.goto('/dashboard');

    // The instructor course picker mounts above the course grid.
    const picker = page.getByRole('heading', { name: 'Import from Canvas' });
    await expect(picker).toBeVisible();

    // The one stubbed Canvas course should render with a "Link" button.
    const linkButton = page.getByRole('button', { name: /link/i }).first();
    await expect(linkButton).toBeVisible();

    await Promise.all([
      page.waitForURL(new RegExp(`/dashboard/courses/${MELI_COURSE_ID}`)),
      linkButton.click(),
    ]);

    expect(page.url()).toContain(`/dashboard/courses/${MELI_COURSE_ID}`);
  });

  test('student joins a Meli course from a Canvas enrollment', async ({
    page,
  }) => {
    await mockCanvasApis(page, { role: 'student' });

    await page.goto('/dashboard');

    // Student dashboard shows a "Join Course" button instead of the
    // instructor picker. Clicking it opens the join-course dialog.
    const joinCourseButton = page.getByRole('button', { name: 'Join Course' });
    await joinCourseButton.click();

    // Dialog mounts the Canvas student-courses section above the
    // enrollment-code form.
    await expect(
      page.getByRole('heading', { name: 'Join a Course' }),
    ).toBeVisible();
    await expect(page.getByText('My Canvas courses')).toBeVisible();

    // The linked Canvas course shows a "Join" action.
    const joinMeliButton = page.getByRole('button', { name: /join/i }).first();
    await expect(joinMeliButton).toBeVisible();

    await Promise.all([
      page.waitForURL(new RegExp(`/dashboard/courses/${MELI_COURSE_ID}`)),
      joinMeliButton.click(),
    ]);

    expect(page.url()).toContain(`/dashboard/courses/${MELI_COURSE_ID}`);
  });
});
