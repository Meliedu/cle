"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Loader2, RefreshCw, FileText, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

interface GenerateSummaryDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

export function GenerateSummaryDialog({
  courseId,
  open,
  onOpenChange,
}: GenerateSummaryDialogProps) {
  const { getToken } = useAuth();
  const [summary, setSummary] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasGenerated, setHasGenerated] = useState(false);

  const generateSummary = useCallback(async () => {
    setIsGenerating(true);
    setError(null);

    try {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      const result = await apiFetch<{ data: { summary: string } }>(
        "/rag/generate-summary",
        {
          method: "POST",
          token: token!,
          body: JSON.stringify({ course_id: courseId }),
        }
      );
      setSummary(result.data.summary);
      setHasGenerated(true);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to generate summary";
      setError(message);
    } finally {
      setIsGenerating(false);
    }
  }, [courseId, getToken]);

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (nextOpen && !hasGenerated && !isGenerating) {
        // Auto-generate on open
        onOpenChange(true);
        generateSummary();
      } else if (!nextOpen) {
        onOpenChange(false);
        // Reset state on close so fresh generation happens next time
        setSummary(null);
        setError(null);
        setHasGenerated(false);
      } else {
        onOpenChange(nextOpen);
      }
    },
    [hasGenerated, isGenerating, onOpenChange, generateSummary]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="size-4 text-[var(--color-primary)]" />
            Course Summary
          </DialogTitle>
          <DialogDescription>
            AI-generated overview of your course materials.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-[200px]">
          {isGenerating ? (
            <div className="space-y-4 py-4">
              <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
                <Loader2 className="size-4 animate-spin text-[var(--color-primary)]" />
                Analyzing course materials...
              </div>
              <div className="space-y-2.5">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center py-8 text-center">
              <p className="text-sm text-[var(--color-error)]">{error}</p>
              <Button
                variant="outline"
                className="mt-4"
                onClick={generateSummary}
              >
                <RefreshCw className="size-4" />
                Try Again
              </Button>
            </div>
          ) : summary ? (
            <div className="space-y-4">
              <div className="max-h-[400px] overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
                <p className="text-sm leading-relaxed text-[var(--color-text-secondary)] whitespace-pre-wrap">
                  {summary}
                </p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={generateSummary}>
                  <RefreshCw className="size-4" />
                  Regenerate
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => handleOpenChange(false)}
                >
                  <X className="size-4" />
                  Close
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
