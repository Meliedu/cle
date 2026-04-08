"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Sparkles } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface GenerateQuizDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

interface FormState {
  readonly title: string;
  readonly numQuestions: string;
}

const initialForm: FormState = {
  title: "",
  numQuestions: "10",
};

const questionCounts = ["5", "10", "15", "20", "30"] as const;

const generationMessages = [
  "Analyzing course materials...",
  "Generating questions...",
] as const;

export function GenerateQuizDialog({
  courseId,
  open,
  onOpenChange,
}: GenerateQuizDialogProps) {
  const { getToken } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(initialForm);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationStep, setGenerationStep] = useState(0);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const stepTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (isGenerating && generationStep === 0) {
      stepTimerRef.current = setTimeout(() => {
        setGenerationStep(1);
      }, 4000);
    }
    return () => {
      if (stepTimerRef.current) {
        clearTimeout(stepTimerRef.current);
      }
    };
  }, [isGenerating, generationStep]);

  const handleSubmit = useCallback(
    async (e: { preventDefault: () => void }) => {
      e.preventDefault();

      if (!form.title.trim()) {
        setTitleError("Quiz title is required");
        return;
      }

      setIsGenerating(true);
      setGenerationStep(0);
      setSubmitError(null);

      try {
        const token = await getToken();
        if (!token) throw new Error("Not authenticated");
        await apiFetch<{ success: boolean }>("/rag/generate-quiz", {
          method: "POST",
          token: token!,
          body: JSON.stringify({
            course_id: courseId,
            title: form.title.trim(),
            num_questions: Number(form.numQuestions),
          }),
        });
        await queryClient.invalidateQueries({
          queryKey: ["quizzes", courseId],
        });
        onOpenChange(false);
        setForm(initialForm);
        setTitleError(null);
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to generate quiz";
        setSubmitError(message);
      } finally {
        setIsGenerating(false);
        setGenerationStep(0);
      }
    },
    [form, courseId, onOpenChange, getToken, queryClient]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen && !isGenerating) {
        setForm(initialForm);
        setTitleError(null);
        setSubmitError(null);
      }
      if (!isGenerating) {
        onOpenChange(nextOpen);
      }
    },
    [onOpenChange, isGenerating]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        {isGenerating ? (
          <div className="flex flex-col items-center py-8">
            <div className="relative mb-6 flex size-16 items-center justify-center">
              <div className="absolute inset-0 animate-ping rounded-full bg-[var(--color-primary-light)] opacity-75" />
              <div className="relative flex size-16 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
                <Sparkles className="size-7 text-[var(--color-primary)]" />
              </div>
            </div>
            <p className="text-sm font-medium text-[var(--color-text)]">
              {generationMessages[generationStep]}
            </p>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              This may take up to 20 seconds
            </p>
            <div className="mt-6 h-1.5 w-48 overflow-hidden rounded-full bg-[var(--color-border)]">
              <div className="h-full animate-pulse rounded-full bg-[var(--color-primary)] transition-all duration-1000" />
            </div>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Generate Quiz</DialogTitle>
              <DialogDescription>
                Create a quiz from your course materials using AI.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="quiz-title">
                  Title <span className="text-[var(--color-error)]">*</span>
                </Label>
                <Input
                  id="quiz-title"
                  placeholder="e.g. Chapter 3 Review"
                  value={form.title}
                  onChange={(e) => {
                    setForm((prev) => ({ ...prev, title: e.target.value }));
                    if (titleError) setTitleError(null);
                  }}
                  aria-invalid={!!titleError}
                />
                {titleError && (
                  <p className="text-xs text-[var(--color-error)]">
                    {titleError}
                  </p>
                )}
              </div>

              <div className="space-y-1.5">
                <Label>Number of Questions</Label>
                <Select
                  value={form.numQuestions}
                  onValueChange={(val) =>
                    setForm((prev) => ({
                      ...prev,
                      numQuestions: val ?? "10",
                    }))
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {questionCounts.map((count) => (
                      <SelectItem key={count} value={count}>
                        {count} questions
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {submitError && (
                <p className="text-sm text-[var(--color-error)]">
                  {submitError}
                </p>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button type="submit">
                  <Sparkles className="size-4" />
                  Generate
                </Button>
              </DialogFooter>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
