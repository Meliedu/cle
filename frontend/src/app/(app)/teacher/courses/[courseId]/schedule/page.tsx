import { CourseScheduleTable } from "@/components/course/course-schedule-table";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface CourseSchedulePageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/schedule` — T030 course schedule table, the
 * "Sessions" tab of the course workspace. Read-only list of course meetings;
 * editing lives in the setup schedule step. Server component: awaits async
 * `params` then renders the shared shell + schedule table.
 */
export default async function CourseSchedulePage({
  params,
}: CourseSchedulePageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="schedule">
      <CourseScheduleTable courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
