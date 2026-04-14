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
import { Loader2, Sparkles } from "lucide-react";
import { apiFetch } from "@/lib/api";
import {
  DocumentSelector,
  useDocumentSelection,
} from "@/components/documents/document-selector";
import { useGenerationJobs } from "@/hooks/use-generation-jobs";

interface EnqueueResponse {
  readonly success: boolean;
  readonly data: {
    readonly job_id: string;
    readonly kind: "generate_flashcards";
    readonly course_id: string;
    readonly title: string | null;
  };
}

interface GenerateFlashcardsDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

const cardCountOptions = [5, 10, 15, 20, 30, 50] as const;

export function GenerateFlashcardsDialog({
  courseId,
  open,
  onOpenChange,
}: GenerateFlashcardsDialogProps) {
  const { getToken } = useAuth();
  const { trackJob } = useGenerationJobs();
  const { selectedIds, setSelectedIds } = useDocumentSelection(courseId);
  const [title, setTitle] = useState("");
  const [numCards, setNumCards] = useState("10");
  const [titleError, setTitleError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleTitleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setTitle(e.target.value);
      if (titleError) {
        setTitleError(null);
      }
    },
    [titleError]
  );

  const handleSubmit = useCallback(
    async (e: { preventDefault: () => void }) => {
      e.preventDefault();

      if (!title.trim()) {
        setTitleError("Title is required");
        return;
      }

      setIsSubmitting(true);
      setSubmitError(null);

      try {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const response = await apiFetch<EnqueueResponse>(
          "/rag/generate-flashcards",
          {
            method: "POST",
            token,
            body: JSON.stringify({
              course_id: courseId,
              title: title.trim(),
              num_cards: Number(numCards),
              document_ids: selectedIds.length > 0 ? selectedIds : undefined,
            }),
          }
        );
        trackJob({
          jobId: response.data.job_id,
          kind: "generate_flashcards",
          courseId,
          title: title.trim(),
        });
        onOpenChange(false);
        setTitle("");
        setNumCards("10");
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
    [title, numCards, courseId, selectedIds, onOpenChange, getToken, trackJob]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setTitle("");
        setNumCards("10");
        setTitleError(null);
        setSubmitError(null);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-[var(--color-primary)]" />
            Generate Flashcards
          </DialogTitle>
          <DialogDescription>
            Create AI-powered flashcards from your course materials.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="flashcard-title">
              Title <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="flashcard-title"
              placeholder="e.g. Chapter 3 Vocabulary"
              value={title}
              onChange={handleTitleChange}
              aria-invalid={!!titleError}
              aria-describedby={
                titleError ? "flashcard-title-error" : undefined
              }
              disabled={isSubmitting}
            />
            {titleError && (
              <p
                id="flashcard-title-error"
                className="text-xs text-[var(--color-error)]"
              >
                {titleError}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Number of Cards</Label>
            <Select
              value={numCards}
              onValueChange={(val) => setNumCards(val ?? "10")}
              disabled={isSubmitting}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select count" />
              </SelectTrigger>
              <SelectContent>
                {cardCountOptions.map((count) => (
                  <SelectItem key={count} value={String(count)}>
                    {count} cards
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DocumentSelector
            courseId={courseId}
            selectedIds={selectedIds}
            onSelectionChange={setSelectedIds}
            disabled={isSubmitting}
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
              disabled={isSubmitting || selectedIds.length === 0}
              title={
                selectedIds.length === 0
                  ? "Upload or select course materials first"
                  : undefined
              }
            >
              {isSubmitting && <Loader2 className="size-4 animate-spin" />}
              {isSubmitting ? "Generating..." : "Generate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
