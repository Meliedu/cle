"use client";

import { useState, useCallback, useMemo } from "react";
import { FileText, CheckSquare, Square, MinusSquare } from "lucide-react";
import { useDocuments, type DocumentResponse } from "@/hooks/use-documents";
import { Skeleton } from "@/components/ui/skeleton";

interface DocumentSelectorProps {
  readonly courseId: string;
  readonly selectedIds: readonly string[];
  readonly onSelectionChange: (ids: string[]) => void;
  readonly disabled?: boolean;
}

export function DocumentSelector({
  courseId,
  selectedIds,
  onSelectionChange,
  disabled = false,
}: DocumentSelectorProps) {
  const { data: documents, isLoading } = useDocuments(courseId);

  const readyDocs = useMemo(
    () => (documents ?? []).filter((d) => d.status === "ready"),
    [documents]
  );

  const allSelected = readyDocs.length > 0 && selectedIds.length === readyDocs.length;
  const noneSelected = selectedIds.length === 0;

  const toggleAll = useCallback(() => {
    if (allSelected) {
      onSelectionChange([]);
    } else {
      onSelectionChange(readyDocs.map((d) => d.id));
    }
  }, [allSelected, readyDocs, onSelectionChange]);

  const toggleDoc = useCallback(
    (docId: string) => {
      if (selectedIds.includes(docId)) {
        onSelectionChange(selectedIds.filter((id) => id !== docId));
      } else {
        onSelectionChange([...selectedIds, docId]);
      }
    },
    [selectedIds, onSelectionChange]
  );

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-8 w-full" />
      </div>
    );
  }

  if (readyDocs.length === 0) {
    return (
      <p className="text-xs text-[var(--color-text-muted)]">
        No processed documents available.
      </p>
    );
  }

  const SelectIcon = allSelected
    ? CheckSquare
    : noneSelected
      ? Square
      : MinusSquare;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[var(--color-text)]">
          Source Documents
        </span>
        <button
          type="button"
          onClick={toggleAll}
          disabled={disabled}
          className="flex items-center gap-1 text-xs text-[var(--color-primary)] hover:underline disabled:opacity-50"
        >
          <SelectIcon className="size-3.5" />
          {allSelected ? "Unselect all" : "Select all"}
        </button>
      </div>
      <div className="max-h-40 space-y-0.5 overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-border)] p-1.5">
        {readyDocs.map((doc) => {
          const checked = selectedIds.includes(doc.id);
          return (
            <label
              key={doc.id}
              className="flex cursor-pointer items-center gap-2 rounded-[var(--radius-sm)] px-2 py-1.5 transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggleDoc(doc.id)}
                disabled={disabled}
                className="size-3.5 accent-[var(--color-primary)]"
              />
              <FileText className="size-3.5 shrink-0 text-[var(--color-text-muted)]" />
              <span className="truncate text-xs text-[var(--color-text)]">
                {doc.filename}
              </span>
            </label>
          );
        })}
      </div>
      <p className="text-xs text-[var(--color-text-muted)]">
        {selectedIds.length} of {readyDocs.length} selected
      </p>
    </div>
  );
}

/** Hook to manage document selection state, defaulting to all ready docs. */
export function useDocumentSelection(courseId: string) {
  const { data: documents } = useDocuments(courseId);
  const readyDocs = useMemo(
    () => (documents ?? []).filter((d) => d.status === "ready"),
    [documents]
  );

  const [selectedIds, setSelectedIds] = useState<string[] | null>(null);

  // Default to all ready docs until user changes selection
  const effectiveIds = selectedIds ?? readyDocs.map((d) => d.id);

  return {
    selectedIds: effectiveIds,
    setSelectedIds: (ids: string[]) => setSelectedIds(ids),
    readyDocs,
  };
}
