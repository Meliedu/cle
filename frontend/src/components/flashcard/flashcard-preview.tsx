"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  Globe,
  GlobeLock,
  Layers,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { DifficultyBadge } from "@/components/ui/difficulty-badge";

interface FlashcardCard {
  readonly id: string;
  readonly card_index: number;
  readonly front: string;
  readonly back: string;
  readonly difficulty: string;
  readonly created_at: string;
}

interface FlashcardSetDetail {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly is_published: boolean;
  readonly cards: readonly FlashcardCard[];
  readonly created_at: string;
}

interface FlashcardPreviewProps {
  readonly setId: string;
  readonly courseId: string;
}

export function FlashcardPreview({ setId, courseId }: FlashcardPreviewProps) {
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();

  const {
    data: fcSet,
    isLoading,
    error,
  } = useQuery<FlashcardSetDetail>({
    queryKey: ["flashcard-set", setId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<{ success: boolean; data: FlashcardSetDetail }>(
        `/flashcard-sets/${setId}`,
        { token: token! }
      );
      return res.data;
    },
    enabled: isSignedIn === true,
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/flashcard-sets/${setId}/publish`, {
        method: "POST",
        token: token!,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flashcard-set", setId] });
      queryClient.invalidateQueries({ queryKey: ["flashcard-sets", courseId] });
    },
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !fcSet) {
    return (
      <Card className="mx-auto max-w-3xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error ? error.message : "Failed to load flashcard set"}
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push(`/dashboard/courses/${courseId}?tab=flashcards`)}
            >
              <ArrowLeft className="size-4" />
            </Button>
            <h1 className="text-xl font-bold text-[var(--color-text)]">
              {fcSet.title}
            </h1>
          </div>
          <div className="flex items-center gap-2 pl-9">
            <Badge
              variant="outline"
              className={
                fcSet.is_published
                  ? "border-[var(--color-success)] text-[var(--color-success)]"
                  : "border-[var(--color-warning)] text-[var(--color-warning)]"
              }
            >
              {fcSet.is_published ? "Published" : "Draft"}
            </Badge>
            <Badge variant="outline">
              <Layers className="size-3" />
              {fcSet.cards.length} cards
            </Badge>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => publishMutation.mutate()}
          disabled={publishMutation.isPending}
        >
          {fcSet.is_published ? (
            <>
              <GlobeLock className="size-4" />
              Unpublish
            </>
          ) : (
            <>
              <Globe className="size-4" />
              Publish
            </>
          )}
        </Button>
      </div>

      <Separator />

      {/* Cards list */}
      <div className="space-y-3">
        {fcSet.cards.map((card, idx) => (
          <Card key={card.id}>
            <CardContent className="space-y-3">
              <div className="flex items-start gap-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-xs font-bold text-[var(--color-primary)]">
                  {idx + 1}
                </span>
                <div className="flex-1 space-y-2">
                  <div className="-mt-1 flex justify-end">
                    <DifficultyBadge value={card.difficulty} size="sm" />
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                      Front
                    </p>
                    <p className="text-sm font-medium text-[var(--color-text)]">
                      {card.front}
                    </p>
                  </div>
                  <Separator />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                      Back
                    </p>
                    <p className="text-sm text-[var(--color-text-secondary)]">
                      {card.back}
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
