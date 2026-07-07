import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentChecklist } from "@/components/student-workspace/student-checklist";

interface StudentChecklistPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/checklist` — S024 student checklist over the
 * work-item spine. Server component: awaits async `params`, then renders the
 * shared shell + checklist.
 */
export default async function StudentChecklistPage({
  params,
}: StudentChecklistPageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="checklist">
      <StudentChecklist courseId={courseId} />
    </StudentCourseShell>
  );
}
