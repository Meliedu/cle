import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { SessionEditForm } from "@/components/course/session-edit-form";

interface SessionEditPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; meetingId: string }>;
}

/**
 * `/teacher/courses/{courseId}/sessions/{meetingId}/edit` — T039 session edit +
 * release-state control. Edits session fields and transitions the student-
 * visibility release state (reusing the P1 meetings release-state PATCH). Server
 * component: awaits async `params` then renders the shared shell + edit form.
 */
export default async function SessionEditPage({ params }: SessionEditPageProps) {
  const { courseId, meetingId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="sessions">
      <SessionEditForm courseId={courseId} meetingId={meetingId} />
    </CourseWorkspaceShell>
  );
}
