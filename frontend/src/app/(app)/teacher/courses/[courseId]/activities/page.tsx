import { CourseActivities } from "@/components/course/course-activities";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface ActivitiesPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/activities` — T060–T075 activities workspace.
 * The `activities` tab is already enabled in the workspace shell; F1 adds this
 * route so the tab resolves. Server component: awaits async `params`, then
 * renders the shared workspace shell with the `activities` tab active. F2–F6
 * replace the placeholder body with the real builders / monitor / grade export.
 */
export default async function ActivitiesPage({ params }: ActivitiesPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <CourseActivities courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
