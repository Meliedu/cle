"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkles, Layers, ArrowRight, Calendar } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { GenerateFlashcardsDialog } from "./generate-flashcards-dialog";

interface FlashcardSet {
  readonly id: string;
  readonly title: string;
  readonly card_count: number;
  readonly created_at: string;
}

interface FlashcardListProps {
  readonly courseId: string;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function FlashcardSetSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-3">
        <Skeleton className="h-5 w-3/4" />
        <div className="flex items-center gap-4">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-4 w-24" />
        </div>
        <Skeleton className="h-8 w-20" />
      </CardContent>
    </Card>
  );
}

export function FlashcardList({ courseId }: FlashcardListProps) {
  const { getToken, isSignedIn } = useAuth();
  const [dialogOpen, setDialogOpen] = useState(false);

  const {
    data: flashcardSets,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["flashcard-sets", courseId],
    queryFn: async (): Promise<readonly FlashcardSet[]> => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const result = await apiFetch<{
        data: readonly FlashcardSet[];
      }>(`/courses/${courseId}/flashcard-sets`, {
        token: token!,
      });
      return result.data;
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });

  const handleOpenDialog = useCallback(() => {
    setDialogOpen(true);
  }, []);

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            Failed to load flashcard sets. Please try again.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--color-text)]">
          Flashcard Sets
        </h3>
        <Button onClick={handleOpenDialog}>
          <Sparkles className="size-4" />
          Generate Flashcards
        </Button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <FlashcardSetSkeleton key={i} />
          ))}
        </div>
      ) : !flashcardSets || flashcardSets.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
              <Layers className="size-6 text-[var(--color-primary)]" />
            </div>
            <h3 className="font-semibold text-[var(--color-text)]">
              No flashcard sets yet
            </h3>
            <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
              Generate flashcards from your course materials to help students
              study and retain key concepts.
            </p>
            <Button className="mt-4" onClick={handleOpenDialog}>
              <Sparkles className="size-4" />
              Generate Your First Set
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {flashcardSets.map((set) => (
            <Card
              key={set.id}
              className="transition-shadow duration-[var(--duration-normal)] hover:shadow-[var(--shadow-md)]"
            >
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Layers className="size-4 shrink-0 text-[var(--color-primary)]" />
                  {set.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
                  <span className="flex items-center gap-1">
                    <Layers className="size-3" />
                    {set.card_count} cards
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="size-3" />
                    {formatDate(set.created_at)}
                  </span>
                </div>
                <Link
                  href={`/dashboard/courses/${courseId}/flashcards/${set.id}`}
                >
                  <Button variant="outline" size="sm" className="mt-1">
                    Study
                    <ArrowRight className="size-3.5" />
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <GenerateFlashcardsDialog
        courseId={courseId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
