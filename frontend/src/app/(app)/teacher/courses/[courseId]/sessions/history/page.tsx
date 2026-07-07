import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { SessionsArchive } from "@/components/course/sessions-archive";

interface SessionsHistoryPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/sessions/history` — T049/T050 checkpoint history +
 * completed-sessions archive. The read-only record of closed checkpoints (each
 * linking into its studio results) and taught sessions, with a designed no-data
 * state (T051). Server component: awaits async `params`, then renders the shared
 * course shell (Sessions tab) + archive.
 */
export default async function SessionsHistoryPage({
  params,
}: SessionsHistoryPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="sessions">
      <SessionsArchive courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
