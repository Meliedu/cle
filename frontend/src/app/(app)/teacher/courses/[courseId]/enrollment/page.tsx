import { EnrollmentOverview } from "@/components/course/enrollment-overview";
import { RosterDetail } from "@/components/course/roster-detail";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface CourseEnrollmentPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/enrollment` — the "Enrollment" tab of the
 * course workspace. Hosts the T031 enrollment overview (counts + join access
 * state) and the T032 class roster as anchored sections on one page. The T033
 * join-request approval section (`#requests`) and T034 code modal are added to
 * this same page in Task 15. Server component: awaits async `params` then
 * renders the shared shell + client sections.
 */
export default async function CourseEnrollmentPage({
  params,
}: CourseEnrollmentPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="enrollment">
      <div className="space-y-10">
        <EnrollmentOverview courseId={courseId} />
        <div id="roster" className="scroll-mt-24">
          <RosterDetail courseId={courseId} />
        </div>
      </div>
    </CourseWorkspaceShell>
  );
}
