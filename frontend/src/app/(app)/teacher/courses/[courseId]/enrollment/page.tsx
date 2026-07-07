import { EnrollmentOverview } from "@/components/course/enrollment-overview";
import { RosterDetail } from "@/components/course/roster-detail";
import { JoinRequestApproval } from "@/components/course/join-request-approval";
import { CourseCodeModal } from "@/components/course/course-code-modal";
import { ScoreCategoriesView } from "@/components/course/score-categories-view";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface CourseEnrollmentPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/enrollment` — the "Enrollment" tab of the
 * course workspace. Hosts the T031 enrollment overview (counts + join access
 * state) with a T034 course-code modal for quick code management, the T033
 * join-request approval section (`#requests`), the T032 class roster
 * (`#roster`), and the T035 read-only score-categories reference — all as
 * anchored sections on one page. Server component: awaits async `params` then
 * renders the shared shell + client sections.
 */
export default async function CourseEnrollmentPage({
  params,
}: CourseEnrollmentPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="enrollment">
      <div className="space-y-10">
        <div className="flex justify-end">
          <CourseCodeModal courseId={courseId} />
        </div>
        <EnrollmentOverview courseId={courseId} />
        <div id="requests" className="scroll-mt-24">
          <JoinRequestApproval courseId={courseId} />
        </div>
        <div id="roster" className="scroll-mt-24">
          <RosterDetail courseId={courseId} />
        </div>
        <ScoreCategoriesView courseId={courseId} />
      </div>
    </CourseWorkspaceShell>
  );
}
