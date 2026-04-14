"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
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
import {
  DocumentSelector,
  useDocumentSelection,
} from "@/components/documents/document-selector";
import { useGenerationJobs } from "@/hooks/use-generation-jobs";

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

interface EnqueueResponse {
  readonly success: boolean;
  readonly data: {
    readonly job_id: string;
    readonly kind: "generate_quiz";
    readonly course_id: string;
    readonly title: string | null;
  };
}

export function GenerateQuizDialog({
  courseId,
  open,
  onOpenChange,
}: GenerateQuizDialogProps) {
  const { getToken } = useAuth();
  const { trackJob } = useGenerationJobs();
  const { selectedIds, setSelectedIds } = useDocumentSelection(courseId);
  const [form, setForm] = useState<FormState>(initialForm);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (e: { preventDefault: () => void }) => {
      e.preventDefault();

      if (!form.title.trim()) {
        setTitleError("Quiz title is required");
        return;
      }

      setIsSubmitting(true);
      setSubmitError(null);

      try {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const response = await apiFetch<EnqueueResponse>(
          "/rag/generate-quiz",
          {
            method: "POST",
            token,
            body: JSON.stringify({
              course_id: courseId,
              title: form.title.trim(),
              num_questions: Number(form.numQuestions),
              document_ids: selectedIds.length > 0 ? selectedIds : undefined,
            }),
          }
        );

        trackJob({
          jobId: response.data.job_id,
          kind: "generate_quiz",
          courseId,
          title: form.title.trim(),
        });

        onOpenChange(false);
        setForm(initialForm);
        setTitleError(null);
      } catch (error: unknown) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to start generation";
        setSubmitError(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [form, courseId, selectedIds, onOpenChange, getToken, trackJob]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (isSubmitting) return;
      if (!nextOpen) {
        setForm(initialForm);
        setTitleError(null);
        setSubmitError(null);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange, isSubmitting]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <>
          <DialogHeader>
            <DialogTitle>Generate Quiz</DialogTitle>
            <DialogDescription>
              Create a quiz from your course materials using AI. You can keep
              browsing while it generates; we&apos;ll notify you when it&apos;s
              ready.
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
                  aria-describedby={titleError ? "quiz-title-error" : undefined}
                />
                {titleError && (
                  <p
                    id="quiz-title-error"
                    className="text-xs text-[var(--color-error)]"
                  >
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

              <DocumentSelector
                courseId={courseId}
                selectedIds={selectedIds}
                onSelectionChange={setSelectedIds}
              />

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
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={selectedIds.length === 0 || isSubmitting}
                title={
                  selectedIds.length === 0
                    ? "Upload or select course materials first"
                    : undefined
                }
              >
                <Sparkles className="size-4" />
                {isSubmitting ? "Starting…" : "Generate"}
              </Button>
              {selectedIds.length === 0 && (
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  Upload or select at least one document to enable generation.
                </p>
              )}
            </DialogFooter>
          </form>
        </>
      </DialogContent>
    </Dialog>
  );
}
