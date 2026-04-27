"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import {
  usePronunciationSets,
  usePublishPronunciationSet,
  useDeletePronunciationSet,
  useMovePronunciationSetToFolder,
  type PronunciationSetResponse,
} from "@/hooks/use-pronunciation-sets";
import {
  usePronunciationFolders,
  useCreatePronunciationFolder,
  useRenamePronunciationFolder,
  useDeletePronunciationFolder,
  useMovePronunciationFolder,
} from "@/hooks/use-pronunciation-folders";
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
  Mic,
  ArrowRight,
  Eye,
  Calendar,
  Globe,
} from "lucide-react";
import { GeneratePronunciationDialog } from "./generate-pronunciation-dialog";
import {
  FolderBrowser,
  ItemActionsMenu,
} from "@/components/folders/folder-browser";

interface PronunciationListProps {
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

function PronunciationSetSkeleton() {
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

export function PronunciationList({
  courseId,
  isInstructor,
}: PronunciationListProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] =
    useState<PronunciationSetResponse | null>(null);

  const { data: sets, isLoading, error } = usePronunciationSets(courseId);
  const { data: folders } = usePronunciationFolders(courseId);
  const createFolder = useCreatePronunciationFolder(courseId);
  const renameFolder = useRenamePronunciationFolder(courseId);
  const deleteFolder = useDeletePronunciationFolder(courseId);
  const moveFolder = useMovePronunciationFolder(courseId);
  const moveSet = useMovePronunciationSetToFolder(courseId);
  const publishMutation = usePublishPronunciationSet(courseId);
  const deleteMutation = useDeletePronunciationSet(courseId);

  const handleDelete = useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id, {
        onSuccess: () => setDeleteTarget(null),
      });
    }
  }, [deleteTarget, deleteMutation]);

  const visibleSets = isInstructor
    ? sets
    : sets?.filter((s) => s.is_published);

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            Failed to load pronunciation sets. Please try again.
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
            <PronunciationSetSkeleton key={i} />
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
              <Mic className="size-6 text-[var(--color-primary)]" />
            </div>
            <h3 className="font-semibold text-[var(--color-text)]">
              No pronunciation sets yet
            </h3>
            <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
              Your instructor hasn&apos;t published any pronunciation sets yet.
              Check back later.
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
        itemSectionLabel="Pronunciation Sets"
        emptyTitle="No pronunciation sets yet"
        emptyBody="Group related sets into folders by topic, or generate your first set from course materials."
        itemCountNoun={{ singular: "set", plural: "sets" }}
        newMenuActions={[
          {
            key: "generate",
            label: "Generate pronunciation set",
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

      <GeneratePronunciationDialog
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
            <DialogTitle>Delete Pronunciation Set</DialogTitle>
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
  set: PronunciationSetResponse;
  courseId: string;
}) {
  return (
    <Card className="transition-shadow duration-[var(--duration-normal)] hover:shadow-[var(--shadow-md)]">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <Mic className="size-4 shrink-0 text-[var(--color-primary)]" />
          <h3 className="line-clamp-2 font-semibold text-[var(--color-text)]">
            {set.title}
          </h3>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <span className="flex items-center gap-1">
            <Mic className="size-3" />
            {set.item_count} items
          </span>
          <span className="flex items-center gap-1">
            <Calendar className="size-3" />
            {formatDate(set.created_at)}
          </span>
        </div>
        <Link href={`/dashboard/courses/${courseId}/pronunciation/${set.id}`}>
          <Button variant="outline" size="sm" className="mt-1">
            Practice
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
  readonly set: PronunciationSetResponse;
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
      <Link href={`/dashboard/courses/${courseId}/pronunciation/${set.id}`}>
        <div className="space-y-3 p-4 pr-10">
          <div className="flex items-start gap-2">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
              <Mic className="size-5" />
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
              <Mic className="size-3" />
              {set.item_count} items
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
