"use client";

import { use } from "react";
import { FlashcardPlayer } from "@/components/flashcard/flashcard-player";

interface Props {
  params: Promise<{ courseId: string; setId: string }>;
}

export default function FlashcardPage({ params }: Props) {
  const { courseId, setId } = use(params);
  return <FlashcardPlayer setId={setId} courseId={courseId} />;
}
