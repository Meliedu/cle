import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { EmptyState } from "@/components/patterns";

interface InsightsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/insights` — T076–T079 course-insights workspace.
 * F1 flips the `insights` tab to enabled and adds this route so the tab
 * resolves; F5 replaces the placeholder body with the real course-insights view
 * (`useCourseInsights`) + signal detail drawer, keeping the designed empty state
 * for a genuinely evidence-free course. Server component: awaits async `params`,
 * then renders the shared workspace shell with the `insights` tab active.
 */
export default async function InsightsPage({ params }: InsightsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="insights">
      <EmptyState
        variant="waiting"
        title="No evidence yet"
        reason="Insights appear here once students start completing checkpoints and practice. Their responses build a source-linked picture of what your class has understood — reviewed by you before anything reaches a student."
      />
    </CourseWorkspaceShell>
  );
}
