"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@/hooks/use-auth";
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
import {
  DifficultySelector,
  type Difficulty,
} from "@/components/ui/difficulty-selector";
import type { PronunciationItemType } from "@/hooks/use-pronunciation-sets";

interface EnqueueResponse {
  readonly success: boolean;
  readonly data: {
    readonly job_id: string;
    readonly kind: "generate_pronunciation";
    readonly course_id: string;
    readonly title: string | null;
  };
}

interface GeneratePronunciationDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

const itemCountOptions = [5, 10, 15, 20, 30] as const;
const itemTypeOptions: readonly {
  readonly value: PronunciationItemType;
  readonly label: string;
}[] = [
  { value: "word", label: "Word" },
  { value: "phrase", label: "Phrase" },
  { value: "sentence", label: "Sentence" },
];

const DEFAULT_TYPES: readonly PronunciationItemType[] = ["word", "phrase"];

export function GeneratePronunciationDialog({
  courseId,
  open,
  onOpenChange,
}: GeneratePronunciationDialogProps) {
  const { getToken } = useAuth();
  const { trackJob } = useGenerationJobs();
  const { selectedIds, setSelectedIds } = useDocumentSelection(courseId);
  const [title, setTitle] = useState("");
  const [numItems, setNumItems] = useState("10");
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [itemTypes, setItemTypes] =
    useState<readonly PronunciationItemType[]>(DEFAULT_TYPES);
  const [titleError, setTitleError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const toggleType = useCallback((t: PronunciationItemType) => {
    setItemTypes((prev) => {
      const has = prev.includes(t);
      const next = has ? prev.filter((x) => x !== t) : [...prev, t];
      // Always keep at least one type selected.
      return next.length > 0 ? next : prev;
    });
  }, []);

  const reset = useCallback(() => {
    setTitle("");
    setNumItems("10");
    setDifficulty("medium");
    setItemTypes(DEFAULT_TYPES);
    setTitleError(null);
    setSubmitError(null);
  }, []);

  const handleTitleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setTitle(e.target.value);
      if (titleError) setTitleError(null);
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
          "/rag/generate-pronunciation",
          {
            method: "POST",
            token,
            body: JSON.stringify({
              course_id: courseId,
              title: title.trim(),
              num_items: Number(numItems),
              document_ids:
                selectedIds.length > 0 ? selectedIds : undefined,
              difficulty,
              item_types: itemTypes,
            }),
          }
        );
        trackJob({
          jobId: response.data.job_id,
          kind: "generate_pronunciation",
          courseId,
          title: title.trim(),
        });
        onOpenChange(false);
        reset();
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
    [
      title,
      numItems,
      difficulty,
      itemTypes,
      courseId,
      selectedIds,
      onOpenChange,
      getToken,
      trackJob,
      reset,
    ]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) reset();
      onOpenChange(nextOpen);
    },
    [onOpenChange, reset]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-[var(--color-primary)]" />
            Generate Pronunciation Set
          </DialogTitle>
          <DialogDescription>
            Create a curated set of pronunciation items from your course
            materials. Students will see it once you publish.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="pronunciation-title">
              Title <span className="text-[var(--color-error)]">*</span>
            </Label>
            <Input
              id="pronunciation-title"
              placeholder="e.g. Lesson 3 Sounds"
              value={title}
              onChange={handleTitleChange}
              aria-invalid={!!titleError}
              aria-describedby={
                titleError ? "pronunciation-title-error" : undefined
              }
              disabled={isSubmitting}
            />
            {titleError && (
              <p
                id="pronunciation-title-error"
                className="text-xs text-[var(--color-error)]"
              >
                {titleError}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Number of Items</Label>
            <Select
              value={numItems}
              onValueChange={(val) => setNumItems(val ?? "10")}
              disabled={isSubmitting}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select count" />
              </SelectTrigger>
              <SelectContent>
                {itemCountOptions.map((count) => (
                  <SelectItem key={count} value={String(count)}>
                    {count} items
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DifficultySelector
            value={difficulty}
            onChange={setDifficulty}
            disabled={isSubmitting}
          />

          <div className="space-y-1.5">
            <Label>Item types</Label>
            <div className="flex gap-2">
              {itemTypeOptions.map((opt) => {
                const active = itemTypes.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleType(opt.value)}
                    disabled={isSubmitting}
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
              Pick one or more. If you pick multiple, the generator mixes them.
            </p>
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
