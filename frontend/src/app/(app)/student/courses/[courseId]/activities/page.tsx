import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentActivities } from "@/components/student-workspace/student-activities";

interface StudentActivitiesPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/activities` — S031 activities placeholder (P5
 * fills it). Server component: awaits async `params`, then renders the shared
 * shell + activities placeholder.
 */
export default async function StudentActivitiesPage({
  params,
}: StudentActivitiesPageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="activities">
      <StudentActivities courseId={courseId} />
    </StudentCourseShell>
  );
}
