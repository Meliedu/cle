"use client";

import { useMemo, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCanvasFiles,
  useImportCanvasFiles,
} from "@/hooks/use-canvas";
import { formatFileSize } from "@/lib/format";
import type { CanvasFileImportResult } from "@/lib/canvas-api";

interface FileImportDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

export function FileImportDialog({
  courseId,
  open,
  onOpenChange,
}: FileImportDialogProps) {
  const { data: files, isLoading } = useCanvasFiles(courseId, open);
  const importFiles = useImportCanvasFiles(courseId);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [lastResult, setLastResult] =
    useState<CanvasFileImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const available = useMemo(() => files?.available ?? [], [files]);
  const alreadyImported = files?.already_imported ?? [];

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === available.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(available.map((f) => f.canvas_file_id)));
    }
  };

  const handleImport = async () => {
    setError(null);
    setLastResult(null);
    try {
      const result = await importFiles.mutateAsync(Array.from(selected));
      setLastResult(result);
      setSelected(new Set());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
    }
  };

  const count = selected.size;
  const allSelected = count > 0 && count === available.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import Canvas files</DialogTitle>
          <DialogDescription>
            Pick files from this Canvas course to copy into Meli. Already-imported
            files are skipped.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-sm text-[var(--color-text-muted)]">
                  {available.length} available ·{" "}
                  {alreadyImported.length} already imported
                </p>
                {available.length > 0 && (
                  <button
                    type="button"
                    onClick={toggleAll}
                    className="text-xs text-[var(--color-primary)] hover:underline"
                  >
                    {allSelected ? "Clear all" : "Select all"}
                  </button>
                )}
              </div>

              {available.length === 0 ? (
                <p className="py-6 text-center text-sm text-[var(--color-text-muted)]">
                  No new files to import.
                </p>
              ) : (
                <ul className="max-h-80 divide-y divide-[var(--color-border)] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-border)]">
                  {available.map((f) => {
                    const checked = selected.has(f.canvas_file_id);
                    return (
                      <li
                        key={f.canvas_file_id}
                        className="flex items-center gap-3 px-3 py-2"
                      >
                        <input
                          type="checkbox"
                          id={`file-${f.canvas_file_id}`}
                          checked={checked}
                          onChange={() => toggle(f.canvas_file_id)}
                          className="size-4 cursor-pointer"
                        />
                        <label
                          htmlFor={`file-${f.canvas_file_id}`}
                          className="flex min-w-0 flex-1 cursor-pointer items-center gap-2"
                        >
                          <FileText className="size-4 shrink-0 text-[var(--color-text-muted)]" />
                          <span className="truncate text-sm text-[var(--color-text)]">
                            {f.display_name || f.filename}
                          </span>
                        </label>
                        <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
                          {f.size ? formatFileSize(f.size) : ""}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </>
          )}

          {error && (
            <p className="text-sm text-[var(--color-error)]">{error}</p>
          )}
          {lastResult && (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm">
              <span className="font-medium text-[var(--color-success)]">
                Imported {lastResult.imported}
              </span>
              <span className="mx-2 text-[var(--color-text-muted)]">·</span>
              <span className="text-[var(--color-text-muted)]">
                Skipped {lastResult.skipped}
              </span>
              {lastResult.errors.length > 0 && (
                <span className="ml-2">
                  <Badge
                    className="bg-[var(--color-error-light)] text-[var(--color-error)]"
                  >
                    {lastResult.errors.length} errors
                  </Badge>
                </span>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={importFiles.isPending}
          >
            Close
          </Button>
          <Button
            onClick={handleImport}
            disabled={count === 0 || importFiles.isPending}
          >
            {importFiles.isPending && (
              <Loader2 className="size-4 animate-spin" />
            )}
            {importFiles.isPending
              ? "Importing…"
              : count > 0
                ? `Import ${count} file${count === 1 ? "" : "s"}`
                : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
