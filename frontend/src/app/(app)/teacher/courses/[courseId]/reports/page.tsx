import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { ReportsWorkspace } from "@/components/reports/reports-workspace";

interface ReportsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/reports` — the T080–T085 report workspace. F1
 * flipped the `reports` tab enabled + added this route shell; F2/F3 fill the
 * body with the real archive / detail / edit and approve / send / export /
 * evidence-appendix / share-settings surfaces (`use-reports.ts`). Server
 * component: awaits async `params`, then renders the shared workspace shell with
 * the `reports` tab active.
 */
export default async function ReportsPage({ params }: ReportsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="reports">
      <ReportsWorkspace courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
