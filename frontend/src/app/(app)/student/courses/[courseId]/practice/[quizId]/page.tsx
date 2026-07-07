import { PracticeRunner } from "@/components/practice";

interface StudentPracticePageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/student/courses/{courseId}/practice/{quizId}` — student practice flow
 * (F7 / S043–S049). Server component: awaits async `params`, then hands the ids
 * to the client runner (start → question renderers → feedback → complete).
 */
export default async function StudentPracticePage({
  params,
}: StudentPracticePageProps) {
  const { courseId, quizId } = await params;
  return <PracticeRunner courseId={courseId} quizId={quizId} />;
}
