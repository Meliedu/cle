"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { useQuizzes, useUpdateQuiz } from "@/hooks/use-quizzes";
import {
  useQuizFolders,
  useCreateQuizFolder,
  useRenameQuizFolder,
  useDeleteQuizFolder,
  useMoveQuizFolder,
  useMoveQuizToFolder,
} from "@/hooks/use-quiz-folders";
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
import { Input } from "@/components/ui/input";
import {
  Sparkles,
  Globe,
  Clock,
  HelpCircle,
  PlayCircle,
  Eye,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { GenerateQuizDialog } from "@/components/quiz/generate-quiz-dialog";
import {
  FolderBrowser,
  ItemActionsMenu,
} from "@/components/folders/folder-browser";
import type { QuizResponse } from "@/hooks/use-quizzes";

type Quiz = QuizResponse;

interface QuizListProps {
  readonly courseId: string;
  readonly isInstructor: boolean;
}

function relativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 7) return date.toLocaleDateString();
  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  if (diffMinutes > 0) return `${diffMinutes}m ago`;
  return "Just now";
}

function QuizCardSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <div className="flex items-center gap-3">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}

export function QuizList({ courseId, isInstructor }: QuizListProps) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [generateOpen, setGenerateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Quiz | null>(null);
  const [renameTarget, setRenameTarget] = useState<Quiz | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const { data: quizzes, isLoading, error } = useQuizzes(
    courseId,
    "after_class"
  );
  const { data: folders } = useQuizFolders(
    courseId,
    isInstructor ? "after_class" : undefined
  );
  const createFolder = useCreateQuizFolder(courseId);
  const renameFolder = useRenameQuizFolder(courseId);
  const deleteFolder = useDeleteQuizFolder(courseId);
  const moveFolder = useMoveQuizFolder(courseId);
  const moveQuiz = useMoveQuizToFolder(courseId);
  const updateQuiz = useUpdateQuiz(courseId);

  const publishMutation = useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}/publish`, {
        method: "POST",
        token,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}`, {
        method: "DELETE",
        token,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      setDeleteTarget(null);
    },
  });

  const handleDelete = useCallback(() => {
    if (deleteTarget) {
      deleteMutation.mutate(deleteTarget.id);
    }
  }, [deleteTarget, deleteMutation]);

  const openRename = useCallback((quiz: Quiz) => {
    setRenameTarget(quiz);
    setRenameValue(quiz.title);
  }, []);

  const handleRename = useCallback(() => {
    if (!renameTarget) return;
    const next = renameValue.trim();
    if (!next || next === renameTarget.title) {
      setRenameTarget(null);
      return;
    }
    updateQuiz.mutate(
      { quiz_id: renameTarget.id, title: next },
      { onSuccess: () => setRenameTarget(null) }
    );
  }, [renameTarget, renameValue, updateQuiz]);

  const visibleQuizzes = isInstructor
    ? quizzes
    : quizzes?.filter((q) => q.is_published);

  if (isLoading) {
    return (
      <div className="space-y-4">
        {isInstructor && (
          <div className="flex justify-end">
            <Skeleton className="h-8 w-36" />
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <QuizCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error
              ? error.message
              : "Failed to load quizzes"}
          </p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() =>
              queryClient.invalidateQueries({
                queryKey: ["quizzes", courseId],
              })
            }
          >
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  /* --------------------------------------------------------------- */
  /* Student view — flat grid of published quizzes, no folders       */
  /* --------------------------------------------------------------- */
  if (!isInstructor) {
    if (!visibleQuizzes || visibleQuizzes.length === 0) {
      return (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
              <HelpCircle className="size-6 text-[var(--color-primary)]" />
            </div>
            <h3 className="font-semibold text-[var(--color-text)]">
              No quizzes yet
            </h3>
            <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
              Your instructor hasn't published any quizzes yet. Check back soon.
            </p>
          </CardContent>
        </Card>
      );
    }
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {visibleQuizzes.map((quiz) => (
          <QuizCardItem
            key={quiz.id}
            quiz={quiz}
            courseId={courseId}
            isInstructor={false}
          />
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
        items={visibleQuizzes ?? []}
        itemSectionLabel="Quizzes"
        emptyTitle="No quizzes yet"
        emptyBody="Create a folder to organize practice by chapter or week, or generate your first quiz from course materials."
        itemCountNoun={{ singular: "item", plural: "items" }}
        newMenuActions={[
          {
            key: "generate",
            label: "Generate quiz",
            icon: <Sparkles className="size-4" />,
            onClick: () => setGenerateOpen(true),
          },
        ]}
        sortItems={(a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        }
        onCreateFolder={(parentId, name) =>
          createFolder.mutate({
            name,
            parent_id: parentId,
            purpose: "after_class",
          })
        }
        onRenameFolder={(id, name) =>
          renameFolder.mutate({ folder_id: id, name })
        }
        onDeleteFolder={(id) => deleteFolder.mutate(id)}
        onMoveFolder={(id, parentId) =>
          moveFolder.mutate({ folder_id: id, parent_id: parentId })
        }
        onMoveItem={(quizId, folderId) =>
          moveQuiz.mutate({ quiz_id: quizId, folder_id: folderId })
        }
        renderItem={(quiz, { onMove }) => (
          <InstructorQuizCard
            quiz={quiz}
            courseId={courseId}
            onPublish={() => publishMutation.mutate(quiz.id)}
            isPublishing={
              publishMutation.isPending &&
              publishMutation.variables === quiz.id
            }
            onDelete={() => setDeleteTarget(quiz)}
            onMove={onMove}
            onRename={() => openRename(quiz)}
          />
        )}
      />

      <GenerateQuizDialog
        courseId={courseId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
      />

      <Dialog
        open={renameTarget !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !updateQuiz.isPending) setRenameTarget(null);
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Rename quiz</DialogTitle>
            <DialogDescription>
              Pick a new name for this question set.
            </DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleRename();
            }}
            placeholder="Quiz name"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameTarget(null)}
              disabled={updateQuiz.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={handleRename}
              disabled={
                updateQuiz.isPending ||
                !renameValue.trim() ||
                renameValue.trim() === renameTarget?.title
              }
            >
              {updateQuiz.isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Quiz</DialogTitle>
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
/* Student / public quiz card (flat list)                             */
/* ------------------------------------------------------------------ */
interface QuizCardItemProps {
  readonly quiz: Quiz;
  readonly courseId: string;
  readonly isInstructor: boolean;
}

function QuizCardItem({ quiz, courseId, isInstructor }: QuizCardItemProps) {
  const { is_published: isPublished } = quiz;
  return (
    <Card className="group relative transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      <Link href={`/dashboard/courses/${courseId}/quizzes/${quiz.id}`}>
        <CardContent className="space-y-3">
          <div className="flex items-start justify-between gap-2 pr-6">
            <h3 className="font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
              {quiz.title}
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={isPublished ? "default" : "secondary"}
              className={
                isPublished
                  ? "bg-[oklch(90%_0.05_145)] text-[var(--color-success)] border-transparent"
                  : ""
              }
            >
              {isPublished ? "Published" : "Draft"}
            </Badge>
            <Badge variant="outline">
              <HelpCircle className="size-3" />
              {quiz.question_count} questions
            </Badge>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
              <Clock className="size-3" />
              {relativeDate(quiz.created_at)}
            </span>
            {isInstructor ? (
              <span className="flex items-center gap-1 text-xs font-medium text-[var(--color-text-muted)]">
                <Eye className="size-3.5" />
                Preview
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-[var(--color-primary)]">
                <PlayCircle className="size-3.5" />
                Take Quiz
              </span>
            )}
          </div>
        </CardContent>
      </Link>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Instructor quiz card (rendered inside FolderBrowser)               */
/* ------------------------------------------------------------------ */
interface InstructorQuizCardProps {
  readonly quiz: Quiz;
  readonly courseId: string;
  readonly onPublish: () => void;
  readonly isPublishing: boolean;
  readonly onDelete: () => void;
  readonly onMove: () => void;
  readonly onRename: () => void;
}

function InstructorQuizCard({
  quiz,
  courseId,
  onPublish,
  isPublishing,
  onDelete,
  onMove,
  onRename,
}: InstructorQuizCardProps) {
  const isPublished = quiz.is_published;
  return (
    <div className="group relative h-full overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      <div className="absolute top-3 right-3 z-10 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <ItemActionsMenu
          onMove={onMove}
          onRename={onRename}
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
      <Link href={`/dashboard/courses/${courseId}/quizzes/${quiz.id}`}>
        <div className="space-y-3 p-4 pr-10">
          <h3 className="line-clamp-2 text-sm font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
            {quiz.title}
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={isPublished ? "default" : "secondary"}
              className={
                isPublished
                  ? "bg-[oklch(90%_0.05_145)] text-[var(--color-success)] border-transparent"
                  : ""
              }
            >
              {isPublished ? "Published" : "Draft"}
            </Badge>
            <Badge variant="outline">
              <HelpCircle className="size-3" />
              {quiz.question_count} questions
            </Badge>
          </div>
          <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
            <span className="flex items-center gap-1">
              <Clock className="size-3" />
              {relativeDate(quiz.created_at)}
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
