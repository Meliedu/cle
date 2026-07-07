import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizBuilder } from "@/components/quiz/assessment-quiz-builder";
import { PracticePublishPanel } from "@/components/quiz/practice-publish-panel";
import { PRACTICE_CONFIG } from "@/components/quiz/assessment-config";

interface PracticeBuilderPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string; quizId: string }>;
}

/**
 * `/teacher/courses/{courseId}/practice/{quizId}` — T061/T062/T063 practice
 * builder + review + publish (F2). The shared builder handles question review;
 * the practice publish panel skips the score-policy gate (Decision 7).
 */
export default async function PracticeBuilderPage({
  params,
}: PracticeBuilderPageProps) {
  const { courseId, quizId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizBuilder
        courseId={courseId}
        quizId={quizId}
        config={PRACTICE_CONFIG}
        publishPanel={
          <PracticePublishPanel courseId={courseId} quizId={quizId} />
        }
      />
    </CourseWorkspaceShell>
  );
}
