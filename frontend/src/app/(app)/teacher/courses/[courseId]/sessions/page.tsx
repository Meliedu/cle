import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { SessionsList } from "@/components/course/sessions-list";

interface SessionsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/sessions` — T037 sessions list, the checkpoint-
 * loop home of the course workspace. Lists every session with its release state
 * and a checkpoint-status summary, drilling into the session detail. Server
 * component: awaits async `params` then renders the shared shell + list.
 */
export default async function SessionsPage({ params }: SessionsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="sessions">
      <SessionsList courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
