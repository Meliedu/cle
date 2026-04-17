"use client";

import { useState } from "react";
import { FileText, Loader2, RefreshCw, Sparkles } from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Links inside AI-generated markdown point at unvetted external content.
// Force target=_blank with rel=noopener,noreferrer so the tab opening the
// link cannot reach back through window.opener and so the referrer header
// does not leak our dashboard URL (which may contain course IDs).
const markdownComponents: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DocumentSelector,
  useDocumentSelection,
} from "@/components/documents/document-selector";
import {
  useCourseSummary,
  useGenerateCourseSummary,
} from "@/hooks/use-course-summary";
import { formatRelativeTime } from "@/lib/format";

interface SummaryCardProps {
  readonly courseId: string;
  readonly isInstructor: boolean;
}

export function SummaryCard({ courseId, isInstructor }: SummaryCardProps) {
  const { data: summary, isLoading } = useCourseSummary(courseId);
  const generate = useGenerateCourseSummary(courseId);
  const { selectedIds, setSelectedIds } = useDocumentSelection(courseId);
  const [pickerOpen, setPickerOpen] = useState(false);

  const runGenerate = () => {
    generate.mutate(
      { documentIds: selectedIds },
      {
        onSuccess: () => {
          setPickerOpen(false);
        },
      }
    );
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="size-4 text-[var(--color-primary)]" />
            AI Course Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <FileText className="size-4 text-[var(--color-primary)]" />
              AI Course Summary
            </CardTitle>
            {summary ? (
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Last updated {formatRelativeTime(summary.updated_at)}
              </p>
            ) : (
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {isInstructor
                  ? "Generate an overview of your course materials."
                  : "Your instructor hasn't generated a summary yet."}
              </p>
            )}
          </div>
          {isInstructor && summary && !pickerOpen && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPickerOpen(true)}
              disabled={generate.isPending}
            >
              <RefreshCw className="size-4" />
              Regenerate
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {generate.isError && (
          <p className="text-sm text-[var(--color-error)]">
            {generate.error instanceof Error
              ? generate.error.message
              : "Failed to generate summary"}
          </p>
        )}

        {isInstructor && (!summary || pickerOpen) && (
          <div className="space-y-3">
            <DocumentSelector
              courseId={courseId}
              selectedIds={selectedIds}
              onSelectionChange={setSelectedIds}
              disabled={generate.isPending}
            />
            <div className="flex items-center gap-2">
              <Button
                onClick={runGenerate}
                disabled={selectedIds.length === 0 || generate.isPending}
              >
                {generate.isPending ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Starting…
                  </>
                ) : (
                  <>
                    <Sparkles className="size-4" />
                    {summary ? "Regenerate Summary" : "Generate Summary"}
                  </>
                )}
              </Button>
              {pickerOpen && (
                <Button
                  variant="ghost"
                  onClick={() => setPickerOpen(false)}
                  disabled={generate.isPending}
                >
                  Cancel
                </Button>
              )}
              {selectedIds.length === 0 && (
                <p className="text-xs text-[var(--color-text-muted)]">
                  Select at least one ready document.
                </p>
              )}
            </div>
          </div>
        )}

        {summary && !pickerOpen && (
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-4">
            <div className="prose-summary text-sm leading-relaxed text-[var(--color-text-secondary)]">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {summary.summary_text}
              </ReactMarkdown>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
