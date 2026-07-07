import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentScheduleTable } from "@/components/student-workspace/student-schedule-table";

interface StudentSchedulePageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/schedule` — S025 read-only class schedule table.
 * Server component: awaits async `params`, then renders the shared shell +
 * schedule table.
 */
export default async function StudentSchedulePage({
  params,
}: StudentSchedulePageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="schedule">
      <StudentScheduleTable courseId={courseId} />
    </StudentCourseShell>
  );
}
