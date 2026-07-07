import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizList } from "@/components/quiz/assessment-quiz-list";
import { QUIZ_CONFIG } from "@/components/quiz/assessment-config";

interface QuizPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/quiz` — T064 graded-quiz home (F3). Lists the
 * course's graded quizzes (split from practice by `assessment_purpose`) and
 * opens the shared builder with the score-policy publish gate.
 */
export default async function QuizPage({ params }: QuizPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizList courseId={courseId} config={QUIZ_CONFIG} />
    </CourseWorkspaceShell>
  );
}
