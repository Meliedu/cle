import { Suspense } from "react";

import { SetupWizard } from "./setup-wizard";

interface SetupPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * Wizard shell for `/teacher/courses/{courseId}/setup`. Server component: it
 * awaits the async `params` (Next.js 16) and hands the id to the client
 * orchestrator, which reads/writes setup state and renders the active step.
 * Wrapped in Suspense because the client wizard reads `useSearchParams`.
 */
export default async function CourseSetupPage({ params }: SetupPageProps) {
  const { courseId } = await params;
  return (
    <Suspense fallback={null}>
      <SetupWizard courseId={courseId} />
    </Suspense>
  );
}
