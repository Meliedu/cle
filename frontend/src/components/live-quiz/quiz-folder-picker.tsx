"use client";

import { useMemo, useState } from "react";
import { ChevronRight, Folder, FileQuestion, Home, Check } from "lucide-react";
import { folderHueFor } from "@/components/folders/folder-browser";
import type { QuizFolder } from "@/hooks/use-quiz-folders";
import type { QuizResponse } from "@/hooks/use-quizzes";

export interface QuizFolderPickerProps {
  readonly folders: readonly QuizFolder[];
  readonly quizzes: readonly QuizResponse[];
  readonly selectedQuizId: string | null;
  readonly onSelectQuiz: (quizId: string) => void;
}

/**
 * Folder-aware picker used by the Create Session dialog. Shows the same
 * breadcrumb + current-level model as the bank browser, but clicking a quiz
 * selects it instead of opening it. The picker remembers which folder the
 * selected quiz came from and auto-jumps there when the dialog opens.
 */
export function QuizFolderPicker({
  folders,
  quizzes,
  selectedQuizId,
  onSelectQuiz,
}: QuizFolderPickerProps) {
  const byId = useMemo(
    () => new Map(folders.map((f) => [f.id, f])),
    [folders]
  );
  const byParent = useMemo(() => {
    const m = new Map<string | null, QuizFolder[]>();
    for (const f of folders) {
      const bucket = m.get(f.parent_id) ?? [];
      bucket.push(f);
      m.set(f.parent_id, bucket);
    }
    return m;
  }, [folders]);

  // Auto-jump to the folder the selected quiz lives in so the user sees it.
  const initialFolderId = useMemo(() => {
    if (!selectedQuizId) return null;
    return (
      quizzes.find((q) => q.id === selectedQuizId)?.folder_id ?? null
    );
  }, [selectedQuizId, quizzes]);

  const [currentId, setCurrentId] = useState<string | null>(initialFolderId);

  const crumbs = useMemo(() => {
    const out: QuizFolder[] = [];
    let cur = currentId ? byId.get(currentId) : null;
    while (cur) {
      out.unshift(cur);
      cur = cur.parent_id ? byId.get(cur.parent_id) ?? null : null;
    }
    return out;
  }, [currentId, byId]);

  const currentFolders = useMemo(() => {
    return [...(byParent.get(currentId) ?? [])].sort((a, b) =>
      a.name.localeCompare(b.name)
    );
  }, [byParent, currentId]);

  const currentQuizzes = useMemo(() => {
    return quizzes
      .filter((q) => (q.folder_id ?? null) === currentId)
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
  }, [quizzes, currentId]);

  const isEmpty = currentFolders.length === 0 && currentQuizzes.length === 0;

  return (
    <div className="space-y-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-2">
      {/* Breadcrumb */}
      <div className="flex flex-wrap items-center gap-1 px-1 py-0.5 text-xs text-[var(--color-text-muted)]">
        <button
          type="button"
          onClick={() => setCurrentId(null)}
          className="flex items-center gap-1 rounded-[var(--radius-sm)] px-1.5 py-1 font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
        >
          <Home className="size-3.5" />
          Bank
        </button>
        {crumbs.map((c, i) => (
          <span key={c.id} className="flex items-center gap-1">
            <ChevronRight className="size-3 shrink-0" />
            <button
              type="button"
              onClick={() => setCurrentId(c.id)}
              className={`max-w-[150px] truncate rounded-[var(--radius-sm)] px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-hover)] ${
                i === crumbs.length - 1
                  ? "font-medium text-[var(--color-text)]"
                  : ""
              }`}
            >
              {c.name}
            </button>
          </span>
        ))}
      </div>

      {/* List */}
      {isEmpty ? (
        <p className="px-2 py-6 text-center text-xs text-[var(--color-text-muted)]">
          This folder is empty.
        </p>
      ) : (
        <div className="max-h-[280px] space-y-1 overflow-y-auto">
          {currentFolders.map((f) => {
            const hue = folderHueFor(f.id);
            const itemCount =
              (byParent.get(f.id)?.length ?? 0) +
              quizzes.filter((q) => q.folder_id === f.id).length;
            return (
              <button
                key={f.id}
                type="button"
                onClick={() => setCurrentId(f.id)}
                className="flex w-full items-center gap-2 rounded-[var(--radius-md)] px-2 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)]"
              >
                <span
                  className="flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)]"
                  style={{ backgroundColor: hue.bg, color: hue.fg }}
                >
                  <Folder className="size-4" />
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-[var(--color-text)]">
                  {f.name}
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  {itemCount}
                </span>
                <ChevronRight className="size-4 text-[var(--color-text-muted)]" />
              </button>
            );
          })}
          {currentQuizzes.map((q) => {
            const selected = q.id === selectedQuizId;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => onSelectQuiz(q.id)}
                className={`flex w-full items-center gap-2 rounded-[var(--radius-md)] border px-2 py-2 text-left transition-colors ${
                  selected
                    ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                    : "border-transparent hover:bg-[var(--color-surface-hover)]"
                }`}
              >
                <span
                  className={`flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)] ${
                    selected
                      ? "bg-[var(--color-primary)] text-white"
                      : "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                  }`}
                >
                  <FileQuestion className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-[var(--color-text)]">
                    {q.title}
                  </span>
                  <span className="block truncate text-xs text-[var(--color-text-muted)]">
                    {q.question_count} questions
                  </span>
                </span>
                {selected && (
                  <Check className="size-4 shrink-0 text-[var(--color-primary)]" />
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
