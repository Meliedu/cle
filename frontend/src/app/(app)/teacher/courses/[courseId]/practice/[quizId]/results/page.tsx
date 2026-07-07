import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizResults } from "@/components/quiz/assessment-quiz-results";
import { PRACTICE_CONFIG } from "@/components/quiz/assessment-config";

interface PracticeResultsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/teacher/courses/{courseId}/practice/{quizId}/results` — T064 practice
 * results (F2). Reads publish status from the shared quiz detail and shows the
 * designed results scaffold / empty states.
 */
export default async function PracticeResultsPage({
  params,
}: PracticeResultsPageProps) {
  const { courseId, quizId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizResults
        courseId={courseId}
        quizId={quizId}
        config={PRACTICE_CONFIG}
      />
    </CourseWorkspaceShell>
  );
}
