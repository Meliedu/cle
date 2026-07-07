import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentCourseOverview } from "@/components/student-workspace/student-course-overview";

interface StudentCourseOverviewPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}` — the student course-workspace entry (S023
 * overview). Server component: awaits async `params`, then hands the id to the
 * client shell + overview. Mirrors the teacher course-detail entry but on the
 * student lane with its own tab set.
 */
export default async function StudentCourseOverviewPage({
  params,
}: StudentCourseOverviewPageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="overview">
      <StudentCourseOverview courseId={courseId} />
    </StudentCourseShell>
  );
}
