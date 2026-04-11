"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@clerk/nextjs";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
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
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Sparkles,
  MoreHorizontal,
  Globe,
  Trash2,
  Clock,
  HelpCircle,
  PlayCircle,
  Eye,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { GenerateQuizDialog } from "@/components/quiz/generate-quiz-dialog";

interface Quiz {
  readonly id: string;
  readonly title: string;
  readonly question_count: number;
  readonly is_published: boolean;
  readonly created_at: string;
}

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

  if (diffDays > 7) {
    return date.toLocaleDateString();
  }
  if (diffDays > 0) {
    return `${diffDays}d ago`;
  }
  if (diffHours > 0) {
    return `${diffHours}h ago`;
  }
  if (diffMinutes > 0) {
    return `${diffMinutes}m ago`;
  }
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
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const [generateOpen, setGenerateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Quiz | null>(null);

  const {
    data: quizzes,
    isLoading,
    error,
  } = useQuery<Quiz[]>({
    queryKey: ["quizzes", courseId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const response = await apiFetch<{ success: boolean; data: Quiz[] }>(
        `/courses/${courseId}/quizzes`,
        { token: token! }
      );
      return response.data;
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });

  const publishMutation = useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}/publish`, {
        method: "POST",
        token: token!,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (quizId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}`, {
        method: "DELETE",
        token: token!,
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

  return (
    <div className="space-y-4">
      {isInstructor && (
        <div className="flex justify-end">
          <Button onClick={() => setGenerateOpen(true)}>
            <Sparkles className="size-4" />
            Generate Quiz
          </Button>
        </div>
      )}

      {visibleQuizzes && visibleQuizzes.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleQuizzes.map((quiz) => (
            <QuizCardItem
              key={quiz.id}
              quiz={quiz}
              courseId={courseId}
              isInstructor={isInstructor}
              onPublish={() => publishMutation.mutate(quiz.id)}
              onDelete={() => setDeleteTarget(quiz)}
              isPublishing={
                publishMutation.isPending &&
                publishMutation.variables === quiz.id
              }
            />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
              <HelpCircle className="size-6 text-[var(--color-primary)]" />
            </div>
            <h3 className="font-semibold text-[var(--color-text)]">
              No quizzes yet
            </h3>
            <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
              {isInstructor
                ? "Generate your first quiz from course materials to test your students."
                : "Your instructor hasn't published any quizzes yet. Check back soon."}
            </p>
            {isInstructor && (
              <Button className="mt-4" onClick={() => setGenerateOpen(true)}>
                <Sparkles className="size-4" />
                Generate your first quiz
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {isInstructor && (
        <GenerateQuizDialog
          courseId={courseId}
          open={generateOpen}
          onOpenChange={setGenerateOpen}
        />
      )}

      {/* Delete confirmation dialog */}
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

interface QuizCardItemProps {
  readonly quiz: Quiz;
  readonly courseId: string;
  readonly isInstructor: boolean;
  readonly onPublish: () => void;
  readonly onDelete: () => void;
  readonly isPublishing: boolean;
}

function QuizCardItem({
  quiz,
  courseId,
  isInstructor,
  onPublish,
  onDelete,
  isPublishing,
}: QuizCardItemProps) {
  const { is_published: isPublished } = quiz;

  return (
    <Card className="group relative transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      {isInstructor && (
        <div className="absolute top-3 right-3 z-10">
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon-xs"
                  className="opacity-0 transition-opacity duration-[var(--duration-fast)] group-hover:opacity-100 data-popup-open:opacity-100"
                />
              }
            >
              <MoreHorizontal className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={onPublish}
                disabled={isPublishing}
              >
                <Globe className="size-4" />
                {isPublishing
                  ? "Updating..."
                  : isPublished
                    ? "Unpublish"
                    : "Publish"}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onDelete} variant="destructive">
                <Trash2 className="size-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

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
