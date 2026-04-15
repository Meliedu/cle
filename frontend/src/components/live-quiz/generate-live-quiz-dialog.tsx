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
import { Sparkles } from "lucide-react";
import { apiFetch } from "@/lib/api";
import {
  DocumentSelector,
  useDocumentSelection,
} from "@/components/documents/document-selector";
import { useGenerationJobs } from "@/hooks/use-generation-jobs";

interface GenerateLiveQuizDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

type QuestionType = "multiple_choice" | "true_false";
type Difficulty = "easy" | "medium" | "hard" | "mixed";

interface FormState {
  readonly title: string;
  readonly numQuestions: number;
  readonly types: readonly QuestionType[];
  readonly optionCount: number;
  readonly difficulty: Difficulty;
}

const initialForm: FormState = {
  title: "",
  numQuestions: 10,
  types: ["multiple_choice"],
  optionCount: 4,
  difficulty: "medium",
};

interface EnqueueResponse {
  readonly success: boolean;
  readonly data: {
    readonly job_id: string;
    readonly kind: "generate_quiz";
    readonly course_id: string;
    readonly title: string | null;
  };
}

export function GenerateLiveQuizDialog({
  courseId,
  open,
  onOpenChange,
}: GenerateLiveQuizDialogProps) {
  const { getToken } = useAuth();
  const { trackJob } = useGenerationJobs();
  const { selectedIds, setSelectedIds } = useDocumentSelection(courseId);
  const [form, setForm] = useState<FormState>(initialForm);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const toggleType = (t: QuestionType) => {
    setForm((prev) => {
      const has = prev.types.includes(t);
      const next = has
        ? prev.types.filter((x) => x !== t)
        : [...prev.types, t];
      return { ...prev, types: next.length > 0 ? next : prev.types };
    });
  };

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
        const response = await apiFetch<EnqueueResponse>("/rag/generate-quiz", {
          method: "POST",
          token,
          body: JSON.stringify({
            course_id: courseId,
            title: form.title.trim(),
            num_questions: form.numQuestions,
            document_ids: selectedIds.length > 0 ? selectedIds : undefined,
            purpose: "live",
            question_types: form.types,
            mcq_option_count: form.optionCount,
            difficulty: form.difficulty,
          }),
        });
        trackJob({
          jobId: response.data.job_id,
          kind: "generate_quiz",
          courseId,
          title: form.title.trim(),
        });
        onOpenChange(false);
        setForm(initialForm);
      } catch (error: unknown) {
        setSubmitError(
          error instanceof Error ? error.message : "Failed to start generation"
        );
      } finally {
        setIsSubmitting(false);
      }
    },
    [form, courseId, selectedIds, onOpenChange, getToken, trackJob]
  );

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (isSubmitting) return;
      if (!next) {
        setForm(initialForm);
        setTitleError(null);
        setSubmitError(null);
      }
      onOpenChange(next);
    },
    [onOpenChange, isSubmitting]
  );

  const includesMCQ = form.types.includes("multiple_choice");

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate Live Quiz</DialogTitle>
          <DialogDescription>
            Generate questions sized for live play. You pick the mix — multiple
            choice, true/false, or both — along with difficulty and option count.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="live-quiz-title">
              Title <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="live-quiz-title"
              placeholder="e.g. Week 4 Live Review"
              value={form.title}
              onChange={(e) => {
                setForm((p) => ({ ...p, title: e.target.value }));
                if (titleError) setTitleError(null);
              }}
              aria-invalid={!!titleError}
            />
            {titleError && (
              <p className="text-xs text-[var(--color-error)]">{titleError}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Questions</Label>
              <Input
                type="number"
                min={1}
                max={30}
                value={form.numQuestions}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    numQuestions: Math.max(
                      1,
                      Math.min(30, Number(e.target.value) || 1)
                    ),
                  }))
                }
              />
            </div>
            <div className="space-y-1.5">
              <Label>MCQ options</Label>
              <Input
                type="number"
                min={2}
                max={6}
                value={form.optionCount}
                disabled={!includesMCQ}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    optionCount: Math.max(
                      2,
                      Math.min(6, Number(e.target.value) || 4)
                    ),
                  }))
                }
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Question types</Label>
            <div className="flex gap-2">
              {(
                [
                  { v: "multiple_choice", label: "Multiple choice" },
                  { v: "true_false", label: "True / False" },
                ] as const
              ).map((opt) => {
                const active = form.types.includes(opt.v);
                return (
                  <button
                    key={opt.v}
                    type="button"
                    onClick={() => toggleType(opt.v)}
                    className={`flex-1 rounded-[var(--radius-md)] border px-3 py-2 text-sm transition-colors ${
                      active
                        ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] font-medium"
                        : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
                    }`}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-[var(--color-text-muted)]">
              Pick one or both. If you pick both, the generator mixes them.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label>Difficulty</Label>
            <div className="grid grid-cols-4 gap-2">
              {(["easy", "medium", "hard", "mixed"] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setForm((p) => ({ ...p, difficulty: d }))}
                  className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm capitalize transition-colors ${
                    form.difficulty === d
                      ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] font-medium"
                      : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <DocumentSelector
            courseId={courseId}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
          />

          {submitError && (
            <p className="text-sm text-[var(--color-error)]">{submitError}</p>
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
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
