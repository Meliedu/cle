import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { CheckpointStudio } from "@/components/course/checkpoint-studio";

interface CheckpointStudioPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{
    courseId: string;
    meetingId: string;
    checkpointId: string;
  }>;
}

/**
 * `/teacher/courses/{courseId}/sessions/{meetingId}/checkpoints/{checkpointId}` —
 * T040 checkpoint studio. The container for reviewing/editing one checkpoint's
 * cards (T041/T042), its carry-over lineage (T043), and — from T18 — its
 * publish-path lifecycle. Server component: awaits async `params`, then renders
 * the shared course shell (Sessions tab) + studio.
 */
export default async function CheckpointStudioPage({
  params,
}: CheckpointStudioPageProps) {
  const { courseId, meetingId, checkpointId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="sessions">
      <CheckpointStudio
        courseId={courseId}
        meetingId={meetingId}
        checkpointId={checkpointId}
      />
    </CourseWorkspaceShell>
  );
}
