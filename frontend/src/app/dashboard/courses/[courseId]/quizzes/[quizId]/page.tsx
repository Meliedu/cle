"use client";

import { use } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { QuizPlayer } from "@/components/quiz/quiz-player";
import { QuizPreview } from "@/components/quiz/quiz-preview";

interface Props {
  params: Promise<{ courseId: string; quizId: string }>;
}

export default function QuizPage({ params }: Props) {
  const { courseId, quizId } = use(params);
  const { isInstructor, isLoaded } = useRole();

  if (!isLoaded) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  return isInstructor ? (
    <QuizPreview quizId={quizId} courseId={courseId} />
  ) : (
    <QuizPlayer quizId={quizId} courseId={courseId} />
  );
}
