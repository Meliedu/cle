import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizBuilder } from "@/components/quiz/assessment-quiz-builder";
import { QuizPublishPanel } from "@/components/quiz/quiz-publish-panel";
import { QUIZ_CONFIG } from "@/components/quiz/assessment-config";

interface QuizBuilderPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/teacher/courses/{courseId}/quiz/{quizId}` — T065/T066/T067 graded quiz
 * builder + review + publish (F3). The shared builder handles question review;
 * the graded publish panel enforces the score-policy gate and surfaces the 422
 * `SCORE_POLICY_INCOMPLETE` as a blocked banner with jump-to-field.
 */
export default async function QuizBuilderPage({
  params,
}: QuizBuilderPageProps) {
  const { courseId, quizId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizBuilder
        courseId={courseId}
        quizId={quizId}
        config={QUIZ_CONFIG}
        publishPanel={<QuizPublishPanel courseId={courseId} quizId={quizId} />}
      />
    </CourseWorkspaceShell>
  );
}
