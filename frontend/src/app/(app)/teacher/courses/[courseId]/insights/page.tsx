import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { CourseInsightsView } from "@/components/teacher-insights";

interface InsightsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/insights` — T076–T079 course-insights workspace.
 * F1 flipped the `insights` tab enabled + added this route; F5 fills the body
 * with the real `CourseInsightsView` (`useCourseInsights` — cohort mastery,
 * open-alert severity counts, review-queue depth, reviewable-signals list +
 * T077 signal detail drawer) and F6 appends the evidence-source + effectiveness
 * surfaces. The view keeps the designed empty state for a genuinely
 * evidence-free course. Server component: awaits async `params`, then renders
 * the shared workspace shell with the `insights` tab active.
 */
export default async function InsightsPage({ params }: InsightsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="insights">
      <CourseInsightsView courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
