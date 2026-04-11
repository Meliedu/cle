"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  CheckCircle2,
  Globe,
  GlobeLock,
  Trash2,
  ArrowLeft,
  HelpCircle,
  RefreshCw,
  Plus,
  Loader2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface PreviewQuestion {
  readonly id: string;
  readonly question_index: number;
  readonly question_text: string;
  readonly options: Record<string, string> | null;
  readonly correct_answer: string;
  readonly explanation: string | null;
}

interface QuizPreviewData {
  readonly id: string;
  readonly course_id: string;
  readonly title: string;
  readonly description: string | null;
  readonly quiz_type: string;
  readonly is_published: boolean;
  readonly questions: readonly PreviewQuestion[];
  readonly created_at: string;
}

interface QuizPreviewProps {
  readonly quizId: string;
  readonly courseId: string;
}

const EMPTY_FORM = {
  question_text: "",
  option_a: "",
  option_b: "",
  option_c: "",
  option_d: "",
  correct_answer: "A",
  explanation: "",
};

export function QuizPreview({ quizId, courseId }: QuizPreviewProps) {
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [addOpen, setAddOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["quiz-preview", quizId] });
    queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
  };

  const {
    data: quiz,
    isLoading,
    error,
  } = useQuery<QuizPreviewData>({
    queryKey: ["quiz-preview", quizId],
    queryFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<{ success: boolean; data: QuizPreviewData }>(
        `/quizzes/${quizId}/preview`,
        { token: token! }
      );
      return res.data;
    },
    enabled: isSignedIn === true,
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}/publish`, {
        method: "POST",
        token: token!,
      });
    },
    onSuccess: invalidate,
  });

  const deleteQuizMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/quizzes/${quizId}`, {
        method: "DELETE",
        token: token!,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["quizzes", courseId] });
      router.push(`/dashboard/courses/${courseId}?tab=quizzes`);
    },
  });

  const deleteQuestionMutation = useMutation({
    mutationFn: async (questionId: string) => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(`/questions/${questionId}`, {
        method: "DELETE",
        token: token!,
      });
    },
    onSuccess: invalidate,
  });

  const regenerateMutation = useMutation({
    mutationFn: async (questionId: string) => {
      setRegeneratingId(questionId);
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(
        `/questions/${questionId}/regenerate`,
        { method: "POST", token: token! }
      );
    },
    onSuccess: invalidate,
    onSettled: () => setRegeneratingId(null),
  });

  const addQuestionMutation = useMutation({
    mutationFn: async () => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<{ success: boolean }>(
        `/quizzes/${quizId}/questions`,
        {
          method: "POST",
          token: token!,
          body: JSON.stringify({
            question_text: form.question_text,
            options: {
              A: form.option_a,
              B: form.option_b,
              C: form.option_c,
              D: form.option_d,
            },
            correct_answer: form.correct_answer,
            explanation: form.explanation || null,
          }),
        }
      );
    },
    onSuccess: () => {
      invalidate();
      setAddOpen(false);
      setForm(EMPTY_FORM);
    },
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <Card className="mx-auto max-w-3xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error
              ? error.message
              : "Failed to load quiz preview"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const canAdd =
    form.question_text.trim() &&
    form.option_a.trim() &&
    form.option_b.trim() &&
    form.option_c.trim() &&
    form.option_d.trim();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                router.push(`/dashboard/courses/${courseId}?tab=quizzes`)
              }
            >
              <ArrowLeft className="size-4" />
            </Button>
            <h1 className="text-xl font-bold text-[var(--color-text)]">
              {quiz.title}
            </h1>
          </div>
          <div className="flex items-center gap-2 pl-9">
            <Badge
              variant="outline"
              className={
                quiz.is_published
                  ? "border-[var(--color-success)] text-[var(--color-success)]"
                  : "border-[var(--color-warning)] text-[var(--color-warning)]"
              }
            >
              {quiz.is_published ? "Published" : "Draft"}
            </Badge>
            <Badge variant="outline">
              <HelpCircle className="size-3" />
              {quiz.questions.length} questions
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAddOpen(true)}
          >
            <Plus className="size-4" />
            Add Question
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => publishMutation.mutate()}
            disabled={publishMutation.isPending}
          >
            {quiz.is_published ? (
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => deleteQuizMutation.mutate()}
            disabled={deleteQuizMutation.isPending}
            className="text-[var(--color-error)] hover:bg-[oklch(93%_0.05_25)]"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      {quiz.description && (
        <p className="pl-9 text-sm text-[var(--color-text-secondary)]">
          {quiz.description}
        </p>
      )}

      <Separator />

      {/* Questions */}
      <div className="space-y-4">
        {quiz.questions.map((question, idx) => {
          const options = question.options
            ? Object.entries(question.options)
            : [];
          const isRegenerating = regeneratingId === question.id;

          return (
            <Card
              key={question.id}
              className={isRegenerating ? "opacity-60" : ""}
            >
              <CardContent className="space-y-4">
                <div className="flex items-start gap-3">
                  <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-xs font-bold text-[var(--color-primary)]">
                    {idx + 1}
                  </span>
                  <p className="flex-1 pt-0.5 font-medium text-[var(--color-text)]">
                    {question.question_text}
                  </p>
                </div>

                <div className="ml-10 space-y-2">
                  {options.map(([label, text]) => {
                    const isCorrect = label === question.correct_answer;
                    return (
                      <div
                        key={label}
                        className="flex items-center gap-2 rounded-[var(--radius-md)] border px-3 py-2"
                        style={{
                          borderColor: isCorrect
                            ? "var(--color-success)"
                            : "var(--color-border)",
                          backgroundColor: isCorrect
                            ? "oklch(95% 0.05 145 / 0.3)"
                            : "transparent",
                        }}
                      >
                        <span
                          className="flex size-5 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                          style={{
                            backgroundColor: isCorrect
                              ? "var(--color-success)"
                              : "var(--color-border)",
                            color: isCorrect
                              ? "white"
                              : "var(--color-text-muted)",
                          }}
                        >
                          {isCorrect ? (
                            <CheckCircle2 className="size-3.5" />
                          ) : (
                            label
                          )}
                        </span>
                        <span
                          className="text-sm"
                          style={{
                            color: isCorrect
                              ? "var(--color-success)"
                              : "var(--color-text)",
                            fontWeight: isCorrect ? 600 : 400,
                          }}
                        >
                          {text}
                        </span>
                      </div>
                    );
                  })}
                </div>

                {question.explanation && (
                  <div className="ml-10 rounded-[var(--radius-md)] bg-[var(--color-surface-hover)] px-3 py-2">
                    <p className="text-xs text-[var(--color-text-muted)]">
                      <span className="font-semibold">Explanation:</span>{" "}
                      {question.explanation}
                    </p>
                  </div>
                )}

                {/* Per-question actions */}
                <div className="ml-10 flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => regenerateMutation.mutate(question.id)}
                    disabled={isRegenerating || regenerateMutation.isPending}
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
                  >
                    {isRegenerating ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                    {isRegenerating ? "Regenerating..." : "Regenerate"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      deleteQuestionMutation.mutate(question.id)
                    }
                    disabled={
                      deleteQuestionMutation.isPending ||
                      quiz.questions.length <= 1
                    }
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-error)]"
                  >
                    <Trash2 className="size-3.5" />
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Add Question Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Add Custom Question</DialogTitle>
            <DialogDescription>
              Create a multiple-choice question with four options.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text)]">
                Question
              </label>
              <Input
                placeholder="Enter question text..."
                value={form.question_text}
                onChange={(e) =>
                  setForm((f) => ({ ...f, question_text: e.target.value }))
                }
              />
            </div>

            {(["A", "B", "C", "D"] as const).map((label) => {
              const key = `option_${label.toLowerCase()}` as keyof typeof form;
              return (
                <div key={label} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setForm((f) => ({ ...f, correct_answer: label }))
                    }
                    className="flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors"
                    style={{
                      borderColor:
                        form.correct_answer === label
                          ? "var(--color-success)"
                          : "var(--color-border)",
                      backgroundColor:
                        form.correct_answer === label
                          ? "var(--color-success)"
                          : "transparent",
                      color:
                        form.correct_answer === label
                          ? "white"
                          : "var(--color-text-muted)",
                    }}
                    title={`Mark ${label} as correct answer`}
                  >
                    {label}
                  </button>
                  <Input
                    placeholder={`Option ${label}...`}
                    value={form[key]}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, [key]: e.target.value }))
                    }
                    className="flex-1"
                  />
                </div>
              );
            })}

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-[var(--color-text)]">
                Explanation{" "}
                <span className="font-normal text-[var(--color-text-muted)]">
                  (optional)
                </span>
              </label>
              <Input
                placeholder="Why is this the correct answer..."
                value={form.explanation}
                onChange={(e) =>
                  setForm((f) => ({ ...f, explanation: e.target.value }))
                }
              />
            </div>

            <p className="text-xs text-[var(--color-text-muted)]">
              Click a letter badge to mark it as the correct answer. Currently:{" "}
              <span className="font-semibold text-[var(--color-success)]">
                {form.correct_answer}
              </span>
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => addQuestionMutation.mutate()}
              disabled={!canAdd || addQuestionMutation.isPending}
            >
              {addQuestionMutation.isPending ? "Adding..." : "Add Question"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
