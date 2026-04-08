"use client";

import { use } from "react";
import { QuizPlayer } from "@/components/quiz/quiz-player";

interface Props {
  params: Promise<{ courseId: string; quizId: string }>;
}

export default function QuizPage({ params }: Props) {
  const { courseId, quizId } = use(params);
  return <QuizPlayer quizId={quizId} courseId={courseId} />;
}
