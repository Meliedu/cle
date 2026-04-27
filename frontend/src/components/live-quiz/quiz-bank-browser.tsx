"use client";

import { FileQuestion, Sparkles, Download, Eye } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { FolderBrowser, ItemActionsMenu } from "@/components/folders/folder-browser";
import type { NewMenuAction } from "@/components/folders/folder-browser";
import type { QuizResponse } from "@/hooks/use-quizzes";
import type { QuizFolder } from "@/hooks/use-quiz-folders";
import { formatRelativeTime } from "@/lib/format";

export interface QuizBankBrowserProps {
  readonly folders: readonly QuizFolder[];
  readonly quizzes: readonly QuizResponse[];
  readonly onCreateFolder: (parentId: string | null, name: string) => void;
  readonly onRenameFolder: (folderId: string, name: string) => void;
  readonly onDeleteFolder: (folderId: string) => void;
  readonly onMoveFolder: (folderId: string, parentId: string | null) => void;
  readonly onMoveQuiz: (quizId: string, folderId: string | null) => void;
  readonly onStartSession: (quizId: string) => void;
  readonly onDeleteQuiz: (quizId: string) => void;
  readonly onRenameQuiz: (quizId: string, currentTitle: string) => void;
  readonly onOpenQuiz: (quizId: string) => void;
  readonly onGenerate: () => void;
  readonly onImport: () => void;
}

export function QuizBankBrowser({
  folders,
  quizzes,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onMoveFolder,
  onMoveQuiz,
  onStartSession,
  onDeleteQuiz,
  onRenameQuiz,
  onOpenQuiz,
  onGenerate,
  onImport,
}: QuizBankBrowserProps) {
  const newMenuActions: NewMenuAction[] = [
    {
      key: "generate",
      label: "Generate quiz",
      icon: <Sparkles className="size-4" />,
      onClick: onGenerate,
    },
    {
      key: "import",
      label: "Import from quiz",
      icon: <Download className="size-4" />,
      onClick: onImport,
    },
  ];

  return (
    <FolderBrowser
      folders={folders}
      items={quizzes}
      itemSectionLabel="Quizzes"
      emptyTitle="Nothing here yet"
      emptyBody="Add a folder to organize, or create your first live quiz."
      newMenuActions={newMenuActions}
      itemCountNoun={{ singular: "item", plural: "items" }}
      sortItems={(a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      }
      onCreateFolder={onCreateFolder}
      onRenameFolder={onRenameFolder}
      onDeleteFolder={onDeleteFolder}
      onMoveFolder={onMoveFolder}
      onMoveItem={onMoveQuiz}
      renderItem={(quiz, { view, onMove }) => {
        const openExtra = (
          <DropdownMenuItem onClick={() => onOpenQuiz(quiz.id)}>
            <Eye className="size-4" />
            Review questions
          </DropdownMenuItem>
        );
        const handleActivate = () => onOpenQuiz(quiz.id);
        const handleKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleActivate();
          }
        };
        if (view === "list") {
          return (
            <div
              role="button"
              tabIndex={0}
              onClick={handleActivate}
              onKeyDown={handleKey}
              className="group flex cursor-pointer items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 text-left transition-all hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            >
              <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                <FileQuestion className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-[var(--color-text)]">
                  {quiz.title}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {quiz.question_count} questions ·{" "}
                  {formatRelativeTime(quiz.created_at)}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.stopPropagation();
                  onStartSession(quiz.id);
                }}
              >
                Start
              </Button>
              <ItemActionsMenu
                onMove={onMove}
                onRename={() => onRenameQuiz(quiz.id, quiz.title)}
                onDelete={() => onDeleteQuiz(quiz.id)}
                extra={openExtra}
              />
            </div>
          );
        }
        return (
          <div
            role="button"
            tabIndex={0}
            onClick={handleActivate}
            onKeyDown={handleKey}
            className="group flex h-full cursor-pointer flex-col gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
          >
            <div className="flex items-start justify-between">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                <FileQuestion className="size-5" />
              </span>
              <div className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <ItemActionsMenu
                  onMove={onMove}
                  onRename={() => onRenameQuiz(quiz.id, quiz.title)}
                  onDelete={() => onDeleteQuiz(quiz.id)}
                  extra={openExtra}
                />
              </div>
            </div>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-semibold text-[var(--color-text)]">
                {quiz.title}
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {quiz.question_count} questions ·{" "}
                {formatRelativeTime(quiz.created_at)}
              </p>
            </div>
            <Button
              size="sm"
              className="w-full"
              onClick={(e) => {
                e.stopPropagation();
                onStartSession(quiz.id);
              }}
            >
              Start Session
            </Button>
          </div>
        );
      }}
    />
  );
}

