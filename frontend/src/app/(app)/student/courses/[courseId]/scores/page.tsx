import { StudentScores } from "@/components/student-activities";

interface StudentScoresPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/scores` — the student's own score & participation
 * record (S059). Server component: awaits async `params`, then renders the
 * client `StudentScores` panel over `useMyScores`.
 */
export default async function StudentScoresPage({
  params,
}: StudentScoresPageProps) {
  const { courseId } = await params;
  return <StudentScores courseId={courseId} />;
}
