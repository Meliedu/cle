import { test, expect } from '@playwright/test';

/**
 * Document upload E2E smoke tests.
 *
 * The upload zone lives on a course detail page at
 * /dashboard/courses/[courseId] (Materials tab), which requires
 * authentication. These tests document expected behavior and are
 * marked fixme until Clerk testing tokens are configured.
 *
 * To enable:
 * 1. Set up Clerk Testing Tokens
 *    (https://clerk.com/docs/testing/overview)
 * 2. Inject an authenticated session via storageState or cookies
 * 3. Remove the test.fixme() wrappers
 */

test.describe('Upload zone (requires auth)', () => {
  test.fixme('renders the upload zone with correct instructions', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses/1');

    // Navigate to the Materials tab to reveal the upload zone
    const materialsTab = page.getByRole('tab', { name: 'Materials' });
    await materialsTab.click();

    // The upload zone should display the drag-and-drop instructions
    await expect(
      page.getByText('Drag & drop files or click to browse')
    ).toBeVisible();

    // Accepted file types should be listed
    await expect(
      page.getByText('PDF, DOCX, PPTX, MP4, MP3 - Max 100MB')
    ).toBeVisible();
  });

  test.fixme('shows error for unsupported file type', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses/1');

    // Navigate to the Materials tab
    const materialsTab = page.getByRole('tab', { name: 'Materials' });
    await materialsTab.click();

    // Upload an unsupported file type via the hidden file input
    const fileInput = page.locator('input[type="file"]');

    // Create a fake .exe file to trigger validation
    await fileInput.setInputFiles({
      name: 'malware.exe',
      mimeType: 'application/x-msdownload',
      buffer: Buffer.from('fake-content'),
    });

    // The upload zone should show an error for the unsupported file
    await expect(page.getByText('Unsupported file type')).toBeVisible();
  });

  test.fixme('accepts a valid PDF file and shows upload progress', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses/1');

    // Navigate to the Materials tab
    const materialsTab = page.getByRole('tab', { name: 'Materials' });
    await materialsTab.click();

    // Upload a valid PDF file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'lecture-notes.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('fake-pdf-content'),
    });

    // The file name should appear in the upload list
    await expect(page.getByText('lecture-notes.pdf')).toBeVisible();
  });
});

test.describe('Course detail document list (requires auth)', () => {
  test.fixme('displays existing documents on the Materials tab', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses/1');

    // Navigate to the Materials tab
    const materialsTab = page.getByRole('tab', { name: 'Materials' });
    await materialsTab.click();

    // Sample documents should be listed (from the hardcoded seed data)
    await expect(page.getByText('Chapter 1 - Greetings.pdf')).toBeVisible();
    await expect(page.getByText('Tone Practice Audio.mp3')).toBeVisible();

    // Document statuses should be visible
    await expect(page.getByText('Ready').first()).toBeVisible();
    await expect(page.getByText('Processing')).toBeVisible();
  });

  test.fixme('shows document count in the card header', async ({ page }) => {
    // AUTH REQUIRED: Inject Clerk session before navigating
    await page.goto('/dashboard/courses/1');

    // Navigate to the Materials tab
    const materialsTab = page.getByRole('tab', { name: 'Materials' });
    await materialsTab.click();

    // The document list card header should show the count
    await expect(page.getByText('Documents (5)')).toBeVisible();
  });
});
