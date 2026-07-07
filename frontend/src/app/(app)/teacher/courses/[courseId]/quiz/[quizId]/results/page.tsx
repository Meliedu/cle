import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizResults } from "@/components/quiz/assessment-quiz-results";
import { QUIZ_CONFIG } from "@/components/quiz/assessment-config";

interface QuizResultsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/teacher/courses/{courseId}/quiz/{quizId}/results` — T068 graded quiz
 * results (F3). Reads publish status from the shared quiz detail and shows the
 * designed results scaffold / empty states.
 */
export default async function QuizResultsPage({
  params,
}: QuizResultsPageProps) {
  const { courseId, quizId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizResults
        courseId={courseId}
        quizId={quizId}
        config={QUIZ_CONFIG}
      />
    </CourseWorkspaceShell>
  );
}
