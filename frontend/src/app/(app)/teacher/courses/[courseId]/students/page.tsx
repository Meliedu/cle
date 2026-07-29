import { EnrollmentOverview } from "@/components/course/enrollment-overview";
import { RosterDetail } from "@/components/course/roster-detail";
import { JoinRequestApproval } from "@/components/course/join-request-approval";
import { CourseCodeModal } from "@/components/course/course-code-modal";
import { ScoreCategoriesView } from "@/components/course/score-categories-view";
import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";

interface CourseStudentsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/students`: the Students destination from the
 * approved course rail.
 *
 * This is the former `/enrollment` route under its approved name. Course
 * access lives here rather than on Overview ("Course access is managed under
 * Students, not Overview") so the class code appears exactly once in the route
 * hierarchy. `/enrollment` redirects here for deep links and bookmarks.
 *
 * Sections: T031 enrollment overview (counts + join access), T034 course-code
 * management, T033 join-request approval (`#requests`), T032 class roster
 * (`#roster`), and the T035 read-only score-categories reference.
 */
export default async function CourseStudentsPage({
  params,
}: CourseStudentsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell
      courseId={courseId}
      activeTab="students"
      actions={<CourseCodeModal courseId={courseId} />}
    >
      <div className="space-y-10">
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
