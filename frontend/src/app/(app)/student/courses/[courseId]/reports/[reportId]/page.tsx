import { ReportDetail } from "@/components/student-reports";

interface StudentReportDetailPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; reportId: string }>;
}

/**
 * `/student/courses/{courseId}/reports/{reportId}` — S067 weekly / S068
 * end-term report detail + S069 delivery state. Server component: awaits async
 * `params`, then hands off to the client detail view which fetches the caller's
 * own SENT report and renders its typed body sections + the claim-limits
 * disclaimer verbatim. The detail owns its header because the title/period is
 * data-dependent.
 */
export default async function StudentReportDetailPage({
  params,
}: StudentReportDetailPageProps) {
  const { courseId, reportId } = await params;

  return (
    <div className="mx-auto w-full max-w-2xl py-2">
      <ReportDetail courseId={courseId} reportId={reportId} />
    </div>
  );
}
