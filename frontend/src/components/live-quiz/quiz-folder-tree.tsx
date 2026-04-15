"use client";

import { useMemo, useState } from "react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderPlus,
  BookOpen,
  Pencil,
  Trash2,
  Check,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { formatRelativeTime } from "@/lib/format";
import type { QuizResponse } from "@/hooks/use-quizzes";
import type { QuizFolder } from "@/hooks/use-quiz-folders";

export interface QuizFolderTreeProps {
  readonly folders: readonly QuizFolder[];
  readonly quizzes: readonly QuizResponse[];
  readonly onCreateFolder: (parentId: string | null) => void;
  readonly onRenameFolder: (folderId: string, name: string) => void;
  readonly onDeleteFolder: (folderId: string) => void;
  readonly onMoveQuiz: (quizId: string, folderId: string | null) => void;
  readonly onStartSession: (quizId: string) => void;
  readonly onDeleteQuiz: (quizId: string) => void;
}

interface FolderNode {
  readonly folder: QuizFolder | null; // null => Ungrouped root
  readonly children: FolderNode[];
  readonly quizzes: QuizResponse[];
}

function buildTree(
  folders: readonly QuizFolder[],
  quizzes: readonly QuizResponse[]
): FolderNode {
  const byId = new Map<string, FolderNode>();
  const root: FolderNode = {
    folder: null,
    children: [],
    quizzes: [],
  };
  for (const f of folders) {
    byId.set(f.id, { folder: f, children: [], quizzes: [] });
  }
  for (const f of folders) {
    const node = byId.get(f.id)!;
    if (f.parent_id && byId.has(f.parent_id)) {
      byId.get(f.parent_id)!.children.push(node);
    } else {
      root.children.push(node);
    }
  }
  for (const q of quizzes) {
    if (q.folder_id && byId.has(q.folder_id)) {
      byId.get(q.folder_id)!.quizzes.push(q);
    } else {
      root.quizzes.push(q);
    }
  }
  return root;
}

function flattenFoldersForMenu(
  folders: readonly QuizFolder[]
): { id: string; label: string }[] {
  const byId = new Map<string, QuizFolder>(folders.map((f) => [f.id, f]));
  const depthOf = (id: string): number => {
    let d = 0;
    let cur = byId.get(id);
    while (cur?.parent_id) {
      d += 1;
      cur = byId.get(cur.parent_id);
    }
    return d;
  };
  return folders
    .map((f) => ({
      id: f.id,
      label: `${"— ".repeat(depthOf(f.id))}${f.name}`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function QuizFolderTree(props: QuizFolderTreeProps) {
  const tree = useMemo(
    () => buildTree(props.folders, props.quizzes),
    [props.folders, props.quizzes]
  );
  const folderOptions = useMemo(
    () => flattenFoldersForMenu(props.folders),
    [props.folders]
  );

  return (
    <div className="space-y-2">
      <FolderNodeView
        node={tree}
        depth={0}
        folderOptions={folderOptions}
        {...props}
      />
    </div>
  );
}

interface NodeViewProps extends QuizFolderTreeProps {
  readonly node: FolderNode;
  readonly depth: number;
  readonly folderOptions: { id: string; label: string }[];
}

function FolderNodeView({ node, depth, folderOptions, ...cb }: NodeViewProps) {
  const isRoot = node.folder === null;
  const [expanded, setExpanded] = useState(true);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState(node.folder?.name ?? "");

  const empty = node.children.length === 0 && node.quizzes.length === 0;

  const folderRow = !isRoot && (
    <div
      className="flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1.5 hover:bg-[var(--color-surface-hover)]"
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex size-5 shrink-0 items-center justify-center text-[var(--color-text-muted)]"
        aria-label={expanded ? "Collapse" : "Expand"}
      >
        {expanded ? (
          <ChevronDown className="size-4" />
        ) : (
          <ChevronRight className="size-4" />
        )}
      </button>
      <Folder className="size-4 shrink-0 text-[var(--color-primary)]" />
      {editing ? (
        <div className="flex flex-1 items-center gap-1">
          <Input
            value={draftName}
            autoFocus
            onChange={(e) => setDraftName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                if (draftName.trim()) {
                  cb.onRenameFolder(node.folder!.id, draftName.trim());
                }
                setEditing(false);
              }
              if (e.key === "Escape") {
                setDraftName(node.folder!.name);
                setEditing(false);
              }
            }}
            className="h-7"
          />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              if (draftName.trim()) {
                cb.onRenameFolder(node.folder!.id, draftName.trim());
              }
              setEditing(false);
            }}
          >
            <Check className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraftName(node.folder!.name);
              setEditing(false);
            }}
          >
            <X className="size-4" />
          </Button>
        </div>
      ) : (
        <>
          <span className="flex-1 truncate text-sm font-medium text-[var(--color-text)]">
            {node.folder!.name}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraftName(node.folder!.name);
              setEditing(true);
            }}
            aria-label="Rename folder"
          >
            <Pencil className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => cb.onCreateFolder(node.folder!.id)}
            aria-label="New subfolder"
          >
            <FolderPlus className="size-3.5" />
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => cb.onDeleteFolder(node.folder!.id)}
            aria-label="Delete folder"
          >
            <Trash2 className="size-3.5 text-[var(--color-error)]" />
          </Button>
        </>
      )}
    </div>
  );

  const ungroupedHeader = isRoot && (
    <div className="flex items-center gap-2 px-2 py-1 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
      Ungrouped
    </div>
  );

  return (
    <div>
      {folderRow}
      {ungroupedHeader}
      {(expanded || isRoot) && (
        <>
          {node.quizzes.length === 0 && !isRoot && empty && (
            <div
              className="py-1 text-xs text-[var(--color-text-muted)]"
              style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
            >
              Empty folder
            </div>
          )}
          <div className="space-y-1">
            {node.quizzes.map((q) => (
              <QuizRow
                key={q.id}
                quiz={q}
                depth={depth + (isRoot ? 0 : 1)}
                folderOptions={folderOptions}
                onMoveQuiz={cb.onMoveQuiz}
                onStartSession={cb.onStartSession}
                onDeleteQuiz={cb.onDeleteQuiz}
              />
            ))}
          </div>
          {node.children.map((child) => (
            <FolderNodeView
              key={child.folder!.id}
              node={child}
              depth={depth + (isRoot ? 0 : 1)}
              folderOptions={folderOptions}
              {...cb}
            />
          ))}
        </>
      )}
    </div>
  );
}

interface QuizRowProps {
  readonly quiz: QuizResponse;
  readonly depth: number;
  readonly folderOptions: { id: string; label: string }[];
  readonly onMoveQuiz: (quizId: string, folderId: string | null) => void;
  readonly onStartSession: (quizId: string) => void;
  readonly onDeleteQuiz: (quizId: string) => void;
}

function QuizRow({
  quiz,
  depth,
  folderOptions,
  onMoveQuiz,
  onStartSession,
  onDeleteQuiz,
}: QuizRowProps) {
  return (
    <Card>
      <CardContent
        className="flex items-center gap-3 py-2"
        style={{ paddingLeft: `${depth * 16 + 12}px` }}
      >
        <BookOpen className="size-4 shrink-0 text-[var(--color-primary)]" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-[var(--color-text)]">
            {quiz.title}
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">
            {quiz.question_count} questions ·{" "}
            {formatRelativeTime(quiz.created_at)}
          </p>
        </div>
        <select
          value={quiz.folder_id ?? ""}
          onChange={(e) =>
            onMoveQuiz(quiz.id, e.target.value === "" ? null : e.target.value)
          }
          className="h-8 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs text-[var(--color-text)]"
          aria-label="Move to folder"
        >
          <option value="">Ungrouped</option>
          {folderOptions.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
        <Button size="sm" variant="outline" onClick={() => onStartSession(quiz.id)}>
          Start
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onDeleteQuiz(quiz.id)}
          aria-label="Delete quiz"
        >
          <Trash2 className="size-4 text-[var(--color-error)]" />
        </Button>
      </CardContent>
    </Card>
  );
}
