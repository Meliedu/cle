"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useFlashcardSets } from "@/hooks/use-flashcard-sets";
import {
  useFlashcardFolders,
  useCreateFlashcardFolder,
  useRenameFlashcardFolder,
  useDeleteFlashcardFolder,
  useMoveFlashcardFolder,
  useMoveFlashcardSetToFolder,
} from "@/hooks/use-flashcard-folders";
import { Card, CardContent } from "@/components/ui/card";
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
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import {
  Sparkles,
  Layers,
  ArrowRight,
  Eye,
  Calendar,
  Globe,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { GenerateFlashcardsDialog } from "./generate-flashcards-dialog";
import {
  FolderBrowser,
  ItemActionsMenu,
} from "@/components/folders/folder-browser";
import type { FlashcardSetResponse } from "@/hooks/use-flashcard-sets";

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
  const [deleteTarget, setDeleteTarget] = useState<FlashcardSetResponse | null>(
    null
  );

  const { data: flashcardSets, isLoading, error } = useFlashcardSets(courseId);
  const { data: folders } = useFlashcardFolders(courseId);
  const createFolder = useCreateFlashcardFolder(courseId);
  const renameFolder = useRenameFlashcardFolder(courseId);
  const deleteFolder = useDeleteFlashcardFolder(courseId);
  const moveFolder = useMoveFlashcardFolder(courseId);
  const moveSet = useMoveFlashcardSetToFolder(courseId);

  const publishMutation = useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(
        `/flashcard-sets/${setId}/publish`,
        {
          method: "POST",
          token,
        }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["flashcard-sets", courseId],
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (setId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/flashcard-sets/${setId}`, {
        method: "DELETE",
        token,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["flashcard-sets", courseId],
      });
      setDeleteTarget(null);
    },
  });

  const handleDelete = useCallback(() => {
    if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
  }, [deleteTarget, deleteMutation]);

  const visibleSets = isInstructor
    ? flashcardSets
    : flashcardSets?.filter((s) => s.is_published);

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

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <FlashcardSetSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  /* --------------------------------------------------------------- */
  /* Student view — flat grid                                        */
  /* --------------------------------------------------------------- */
  if (!isInstructor) {
    if (!visibleSets || visibleSets.length === 0) {
      return (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
              <Layers className="size-6 text-[var(--color-primary)]" />
            </div>
            <h3 className="font-semibold text-[var(--color-text)]">
              No flashcard sets yet
            </h3>
            <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
              Your instructor hasn't published any flashcard sets yet. Check
              back later.
            </p>
          </CardContent>
        </Card>
      );
    }
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visibleSets.map((set) => (
          <StudentSetCard key={set.id} set={set} courseId={courseId} />
        ))}
      </div>
    );
  }

  /* --------------------------------------------------------------- */
  /* Instructor view — folder browser                                */
  /* --------------------------------------------------------------- */
  return (
    <div className="space-y-4">
      <FolderBrowser
        folders={folders ?? []}
        items={visibleSets ?? []}
        itemSectionLabel="Flashcard Sets"
        emptyTitle="No flashcard sets yet"
        emptyBody="Group related sets into folders by topic, or generate your first set from course materials."
        itemCountNoun={{ singular: "set", plural: "sets" }}
        newMenuActions={[
          {
            key: "generate",
            label: "Generate flashcards",
            icon: <Sparkles className="size-4" />,
            onClick: () => setDialogOpen(true),
          },
        ]}
        sortItems={(a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        }
        onCreateFolder={(parentId, name) =>
          createFolder.mutate({ name, parent_id: parentId })
        }
        onRenameFolder={(id, name) =>
          renameFolder.mutate({ folder_id: id, name })
        }
        onDeleteFolder={(id) => deleteFolder.mutate(id)}
        onMoveFolder={(id, parentId) =>
          moveFolder.mutate({ folder_id: id, parent_id: parentId })
        }
        onMoveItem={(setId, folderId) =>
          moveSet.mutate({ set_id: setId, folder_id: folderId })
        }
        renderItem={(set, { onMove }) => (
          <InstructorSetCard
            set={set}
            courseId={courseId}
            onPublish={() => publishMutation.mutate(set.id)}
            isPublishing={
              publishMutation.isPending &&
              publishMutation.variables === set.id
            }
            onDelete={() => setDeleteTarget(set)}
            onMove={onMove}
          />
        )}
      />

      <GenerateFlashcardsDialog
        courseId={courseId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />

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
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Student set card                                                   */
/* ------------------------------------------------------------------ */
function StudentSetCard({
  set,
  courseId,
}: {
  set: FlashcardSetResponse;
  courseId: string;
}) {
  return (
    <Card className="transition-shadow duration-[var(--duration-normal)] hover:shadow-[var(--shadow-md)]">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <Layers className="size-4 shrink-0 text-[var(--color-primary)]" />
          <h3 className="line-clamp-2 font-semibold text-[var(--color-text)]">
            {set.title}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <span className="flex items-center gap-1">
            <Layers className="size-3" />
            {set.card_count} cards
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="size-3" />
            {formatDate(set.created_at)}
          </span>
        </div>
        <Link href={`/dashboard/courses/${courseId}/flashcards/${set.id}`}>
          <Button variant="outline" size="sm" className="mt-1">
            Study
            <ArrowRight className="size-3.5" />
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Instructor set card                                                */
/* ------------------------------------------------------------------ */
interface InstructorSetCardProps {
  readonly set: FlashcardSetResponse;
  readonly courseId: string;
  readonly onPublish: () => void;
  readonly isPublishing: boolean;
  readonly onDelete: () => void;
  readonly onMove: () => void;
}

function InstructorSetCard({
  set,
  courseId,
  onPublish,
  isPublishing,
  onDelete,
  onMove,
}: InstructorSetCardProps) {
  const isPublished = set.is_published;
  return (
    <div className="group relative h-full overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      <div className="absolute top-3 right-3 z-10 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <ItemActionsMenu
          onMove={onMove}
          onDelete={onDelete}
          extra={
            <DropdownMenuItem onClick={onPublish} disabled={isPublishing}>
              <Globe className="size-4" />
              {isPublishing
                ? "Updating..."
                : isPublished
                  ? "Unpublish"
                  : "Publish"}
            </DropdownMenuItem>
          }
        />
      </div>
      <Link href={`/dashboard/courses/${courseId}/flashcards/${set.id}`}>
        <div className="space-y-3 p-4 pr-10">
          <div className="flex items-start gap-2">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
              <Layers className="size-5" />
            </span>
            <h3 className="line-clamp-2 text-sm font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
              {set.title}
            </h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
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
            <Badge variant="outline">
              <Layers className="size-3" />
              {set.card_count} cards
            </Badge>
          </div>
          <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
            <span className="flex items-center gap-1">
              <Calendar className="size-3" />
              {formatDate(set.created_at)}
            </span>
            <span className="flex items-center gap-1 font-medium">
              <Eye className="size-3.5" />
              Preview
            </span>
          </div>
        </div>
      </Link>
    </div>
  );
}
