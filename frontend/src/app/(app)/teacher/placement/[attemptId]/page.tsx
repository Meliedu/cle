import { PlacementAttemptReview } from "@/components/placement/placement-attempt-review";

interface PageProps {
  /** Next.js 16 delivers route params as a promise. */
  readonly params: Promise<{ attemptId: string }>;
}

/** `/teacher/placement/{attemptId}` — evidence and the CLE decision. */
export default async function TeacherPlacementAttemptPage({ params }: PageProps) {
  const { attemptId } = await params;
  return <PlacementAttemptReview attemptId={attemptId} />;
}
