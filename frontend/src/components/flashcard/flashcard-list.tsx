"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useFlashcardSets } from "@/hooks/use-flashcard-sets";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Sparkles,
  Layers,
  ArrowRight,
  Eye,
  Calendar,
  MoreHorizontal,
  Globe,
  Trash2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { GenerateFlashcardsDialog } from "./generate-flashcards-dialog";

interface FlashcardSet {
  readonly id: string;
  readonly title: string;
  readonly is_published?: boolean;
  readonly card_count: number;
  readonly created_at: string;
}

interface FlashcardListProps {
  readonly courseId: string;
  readonly isInstructor: boolean;
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

export function FlashcardList({ courseId, isInstructor }: FlashcardListProps) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FlashcardSet | null>(null);

  const {
    data: flashcardSets,
    isLoading,
    error,
  } = useFlashcardSets(courseId) as {
    data: readonly FlashcardSet[] | undefined;
    isLoading: boolean;
    error: unknown;
  };

  const publishMutation = useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/flashcard-sets/${setId}/publish`, {
        method: "POST",
        token,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flashcard-sets", courseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/flashcard-sets/${setId}`, {
        method: "DELETE",
        token,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["flashcard-sets", courseId] });
      setDeleteTarget(null);
    },
  });

  const handleDelete = useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id);
    }
  }, [deleteTarget, deleteMutation]);

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
        {isInstructor && (
          <Button onClick={handleOpenDialog}>
            <Sparkles className="size-4" />
            Generate Flashcards
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
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
              {isInstructor
                ? "Generate flashcards from your course materials to help students study and retain key concepts."
                : "Your instructor hasn't published any flashcard sets yet. Check back later."}
            </p>
            {isInstructor && (
              <Button className="mt-4" onClick={handleOpenDialog}>
                <Sparkles className="size-4" />
                Generate Your First Set
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {flashcardSets.map((set) => {
            const isPublished = set.is_published;

            return (
              <Card
                key={set.id}
                className="transition-shadow duration-[var(--duration-normal)] hover:shadow-[var(--shadow-md)]"
              >
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <CardTitle className="flex items-center gap-2">
                      <Layers className="size-4 shrink-0 text-[var(--color-primary)]" />
                      {set.title}
                    </CardTitle>
                    {isInstructor && (
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <button className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-muted)] transition-colors hover:bg-[var(--color-surface-hover)]">
                              <MoreHorizontal className="size-4" />
                            </button>
                          }
                        />
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => publishMutation.mutate(set.id)}
                          >
                            <Globe className="size-4" />
                            {isPublished ? "Unpublish" : "Publish"}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-[var(--color-error)]"
                            onClick={() => setDeleteTarget(set)}
                          >
                            <Trash2 className="size-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
                    {isInstructor && (
                      <Badge
                        variant="outline"
                        className={
                          isPublished
                            ? "border-[var(--color-success)] text-[var(--color-success)]"
                            : "border-[var(--color-warning)] text-[var(--color-warning)]"
                        }
                      >
                        {isPublished ? "Published" : "Draft"}
                      </Badge>
                    )}
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
                      {isInstructor ? (
                        <>
                          <Eye className="size-3.5" />
                          Preview
                        </>
                      ) : (
                        <>
                          Study
                          <ArrowRight className="size-3.5" />
                        </>
                      )}
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Delete confirmation dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Flashcard Set</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &ldquo;{deleteTarget?.title}
              &rdquo;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <GenerateFlashcardsDialog
        courseId={courseId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  );
}
