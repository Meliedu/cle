import { ActivityRunner } from "@/components/student-activities";

interface StudentActivityPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; activityId: string }>;
}

/**
 * `/student/courses/{courseId}/activities/{activityId}` — the focused single-
 * activity flow (S053–S058, S073). Server component: awaits async `params`,
 * then hands off to the client `ActivityRunner` which drives loading / waiting /
 * format interaction / submitted-record on one mobile-first column.
 */
export default async function StudentActivityPage({
  params,
}: StudentActivityPageProps) {
  const { courseId, activityId } = await params;
  return <ActivityRunner courseId={courseId} activityId={activityId} />;
}
