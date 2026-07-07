import { FollowUpActionDetail } from "@/components/student-insights/follow-up-action-detail";

interface FollowUpDetailPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; followUpId: string }>;
}

/**
 * `/student/courses/{courseId}/follow-ups/{followUpId}` — S061 follow-up action
 * detail over `useFollowUpDetail`. Server component: awaits async `params`, then
 * renders the mobile-first single-column detail. Reached from the checklist's
 * distinct `follow_up` row (S060).
 */
export default async function FollowUpDetailPage({
  params,
}: FollowUpDetailPageProps) {
  const { courseId, followUpId } = await params;
  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-2">
      <FollowUpActionDetail courseId={courseId} followUpId={followUpId} />
    </div>
  );
}
