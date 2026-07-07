import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { SessionDetail } from "@/components/course/session-detail";

interface SessionDetailPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; meetingId: string }>;
}

/**
 * `/teacher/courses/{courseId}/sessions/{meetingId}` — T038 session detail. One
 * session's facts + its checkpoint(s), with links into edit (T039) and the
 * checkpoint studio (T17). Server component: awaits async `params` then renders
 * the shared shell + detail.
 */
export default async function SessionDetailPage({
  params,
}: SessionDetailPageProps) {
  const { courseId, meetingId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="sessions">
      <SessionDetail courseId={courseId} meetingId={meetingId} />
    </CourseWorkspaceShell>
  );
}
