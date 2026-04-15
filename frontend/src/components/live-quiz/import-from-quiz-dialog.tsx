"use client";

import { useEffect, useState } from "react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Check, Download } from "lucide-react";
import {
  useQuizzes,
  useQuiz,
  useImportQuestionsToLive,
} from "@/hooks/use-quizzes";

interface ImportFromQuizDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

export function ImportFromQuizDialog({
  courseId,
  open,
  onOpenChange,
}: ImportFromQuizDialogProps) {
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: afterClassQuizzes, isLoading: listLoading } = useQuizzes(
    courseId,
    "after_class"
  );
  const { data: detail, isLoading: detailLoading } = useQuiz(sourceId ?? "");
  const importMutation = useImportQuestionsToLive(courseId);

  useEffect(() => {
    if (!open) {
      setSourceId(null);
      setSelected(new Set());
      setTitle("");
      setError(null);
    }
  }, [open]);

  useEffect(() => {
    if (detail && !title) {
      setTitle(`${detail.title} (Live)`);
    }
    if (detail) {
      setSelected(new Set(detail.questions.map((q) => q.id)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  const handleToggle = (qid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
  };

  const handleImport = () => {
    if (!sourceId) {
      setError("Pick a source quiz.");
      return;
    }
    if (selected.size === 0) {
      setError("Pick at least one question.");
      return;
    }
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setError(null);
    importMutation.mutate(
      {
        source_quiz_id: sourceId,
        question_ids: Array.from(selected),
        title: title.trim(),
      },
      {
        onSuccess: () => onOpenChange(false),
        onError: (e) => setError(e instanceof Error ? e.message : "Import failed"),
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import questions from a quiz</DialogTitle>
          <DialogDescription>
            Copy questions from an existing after-class quiz into a new live
            quiz. The original quiz is unchanged; you can tweak the copy freely.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Source quiz</Label>
            {listLoading ? (
              <Skeleton className="h-9 w-full" />
            ) : afterClassQuizzes && afterClassQuizzes.length > 0 ? (
              <div className="space-y-1">
                {afterClassQuizzes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => setSourceId(q.id)}
                    className={`w-full rounded-[var(--radius-md)] border px-3 py-2 text-left text-sm transition-colors ${
                      sourceId === q.id
                        ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                        : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
                    }`}
                  >
                    <span className="font-medium text-[var(--color-text)]">
                      {q.title}
                    </span>
                    <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                      {q.question_count} questions
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--color-text-muted)]">
                No after-class quizzes yet.
              </p>
            )}
          </div>

          {sourceId && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="import-title">New live quiz title</Label>
                <Input
                  id="import-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Week 4 — Live"
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label>Questions</Label>
                  {detail && (
                    <button
                      type="button"
                      className="text-xs text-[var(--color-primary)] hover:underline"
                      onClick={() =>
                        setSelected(
                          selected.size === detail.questions.length
                            ? new Set()
                            : new Set(detail.questions.map((q) => q.id))
                        )
                      }
                    >
                      {selected.size === detail?.questions.length
                        ? "Deselect all"
                        : "Select all"}
                    </button>
                  )}
                </div>
                {detailLoading ? (
                  <Skeleton className="h-40 w-full" />
                ) : detail ? (
                  <div className="max-h-60 overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-border)]">
                    {detail.questions.map((q) => (
                      <button
                        key={q.id}
                        type="button"
                        onClick={() => handleToggle(q.id)}
                        className="flex w-full cursor-pointer items-start gap-3 border-b border-[var(--color-border)] px-3 py-2 text-left text-sm last:border-b-0 hover:bg-[var(--color-surface-hover)]"
                      >
                        <span
                          className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border ${
                            selected.has(q.id)
                              ? "border-[var(--color-primary)] bg-[var(--color-primary)]"
                              : "border-[var(--color-border)]"
                          }`}
                        >
                          {selected.has(q.id) && (
                            <Check className="size-3 text-white" />
                          )}
                        </span>
                        <span className="flex-1 text-[var(--color-text)]">
                          <span className="mr-1 text-xs text-[var(--color-text-muted)]">
                            #{q.question_index + 1}
                          </span>
                          {q.question_text}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </>
          )}

          {error && <p className="text-sm text-[var(--color-error)]">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleImport}
            disabled={
              !sourceId || selected.size === 0 || importMutation.isPending
            }
          >
            <Download className="size-4" />
            {importMutation.isPending
              ? "Importing…"
              : `Import ${selected.size || ""} questions`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
