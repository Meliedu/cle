import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { AssessmentQuizList } from "@/components/quiz/assessment-quiz-list";
import { PRACTICE_CONFIG } from "@/components/quiz/assessment-config";

interface PracticePageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/practice` — T060 practice home (F2). Lists the
 * course's practice quizzes (split from graded by `assessment_purpose`) and
 * opens the shared builder / generate flow. Rendered inside the course
 * workspace shell with the Activities tab active.
 */
export default async function PracticePage({ params }: PracticePageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="activities">
      <AssessmentQuizList courseId={courseId} config={PRACTICE_CONFIG} />
    </CourseWorkspaceShell>
  );
}
