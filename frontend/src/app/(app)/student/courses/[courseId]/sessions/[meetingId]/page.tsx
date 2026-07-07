import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentSessionDetail } from "@/components/student-workspace/student-session-detail";

interface StudentSessionDetailPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; meetingId: string }>;
}

/**
 * `/student/courses/{courseId}/sessions/{meetingId}` — S027 session detail (or
 * the S028 locked state when the session isn't released yet). Server component:
 * awaits async `params`, then renders the shared shell + session detail.
 */
export default async function StudentSessionDetailPage({
  params,
}: StudentSessionDetailPageProps) {
  const { courseId, meetingId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="sessions">
      <StudentSessionDetail courseId={courseId} meetingId={meetingId} />
    </StudentCourseShell>
  );
}
