"use client";

import { use } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { PronunciationPlayer } from "@/components/pronunciation/pronunciation-player";
import { PronunciationPreview } from "@/components/pronunciation/pronunciation-preview";

interface Props {
  params: Promise<{ courseId: string; setId: string }>;
}

export default function PronunciationSetPage({ params }: Props) {
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
    <PronunciationPreview setId={setId} courseId={courseId} />
  ) : (
    <PronunciationPlayer setId={setId} courseId={courseId} />
  );
}
