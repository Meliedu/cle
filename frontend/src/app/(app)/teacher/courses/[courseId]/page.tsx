import { CourseOverview } from "@/components/course/course-overview";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface CourseOverviewPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}` — the teacher course-detail entry (T029 course
 * overview). This is the first teacher course-detail route: P1 shipped setup
 * but deferred the workspace. The shell provides the course header + tab nav
 * that P3+ extends (materials / activities / insights); this page renders the
 * overview tab. Server component: awaits async `params` then hands the id to
 * the client shell + overview.
 */
export default async function CourseOverviewPage({
  params,
}: CourseOverviewPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="overview">
      <CourseOverview courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
