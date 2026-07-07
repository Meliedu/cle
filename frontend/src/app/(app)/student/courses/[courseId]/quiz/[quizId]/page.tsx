import { QuizRunner } from "@/components/practice";

interface StudentQuizPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/student/courses/{courseId}/quiz/{quizId}` — student graded-quiz flow
 * (F8 / S050–S052). Server component: awaits async `params`, then hands the ids
 * to the client runner (landing disclosure → taking → result).
 */
export default async function StudentQuizPage({
  params,
}: StudentQuizPageProps) {
  const { courseId, quizId } = await params;
  return <QuizRunner courseId={courseId} quizId={quizId} />;
}
