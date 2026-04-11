"use client";

import { use } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { FlashcardPlayer } from "@/components/flashcard/flashcard-player";
import { FlashcardPreview } from "@/components/flashcard/flashcard-preview";

interface Props {
  params: Promise<{ courseId: string; setId: string }>;
}

export default function FlashcardPage({ params }: Props) {
  const { courseId, setId } = use(params);
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
    <FlashcardPreview setId={setId} courseId={courseId} />
  ) : (
    <FlashcardPlayer setId={setId} courseId={courseId} />
  );
}
