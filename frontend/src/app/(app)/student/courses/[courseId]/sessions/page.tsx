import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentSessionsList } from "@/components/student-workspace/student-sessions-list";

interface StudentSessionsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/sessions` — S026 student sessions list (released
 * + completed only). Server component: awaits async `params`, then renders the
 * shared shell + sessions list.
 */
export default async function StudentSessionsPage({
  params,
}: StudentSessionsPageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="sessions">
      <StudentSessionsList courseId={courseId} />
    </StudentCourseShell>
  );
}
