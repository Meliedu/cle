"use client";

import { useMemo, useState, useEffect } from "react";
import {
  Folder,
  FolderPlus,
  FileQuestion,
  MoreHorizontal,
  ChevronRight,
  Home,
  Pencil,
  Trash2,
  ArrowRight,
  Sparkles,
  Download,
  Plus,
  LayoutGrid,
  Rows3,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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
  readonly onGenerate: () => void;
  readonly onImport: () => void;
}

type ViewMode = "grid" | "list";

interface PromptState {
  readonly mode: "new-folder" | "rename-folder";
  readonly folderId?: string;
  readonly initial?: string;
  readonly parentId?: string | null;
}

interface MoveState {
  readonly type: "folder" | "quiz";
  readonly id: string;
  readonly currentParentId: string | null;
}

/* ------------------------------------------------------------------ */
/* Soft, distinct folder color palette keyed by id. GoodNotes-style   */
/* tinted surfaces: low chroma, harmonious, legible in light + dark.  */
/* ------------------------------------------------------------------ */
const FOLDER_HUES = [
  { bg: "oklch(94% 0.03 250)", fg: "oklch(45% 0.15 250)" },
  { bg: "oklch(94% 0.04 155)", fg: "oklch(45% 0.15 155)" },
  { bg: "oklch(94% 0.04 75)", fg: "oklch(45% 0.15 75)" },
  { bg: "oklch(94% 0.04 25)", fg: "oklch(45% 0.18 25)" },
  { bg: "oklch(94% 0.04 300)", fg: "oklch(45% 0.18 300)" },
  { bg: "oklch(94% 0.04 200)", fg: "oklch(45% 0.15 200)" },
];

function hueFor(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return FOLDER_HUES[h % FOLDER_HUES.length];
}

/* ------------------------------------------------------------------ */
/* Tree helpers                                                       */
/* ------------------------------------------------------------------ */

function buildChildrenMap(folders: readonly QuizFolder[]) {
  const byParent = new Map<string | null, QuizFolder[]>();
  for (const f of folders) {
    const key = f.parent_id;
    const bucket = byParent.get(key) ?? [];
    bucket.push(f);
    byParent.set(key, bucket);
  }
  return byParent;
}

function getAncestors(
  folderId: string | null,
  byId: Map<string, QuizFolder>
): QuizFolder[] {
  const crumbs: QuizFolder[] = [];
  let cur = folderId ? byId.get(folderId) : null;
  while (cur) {
    crumbs.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) ?? null : null;
  }
  return crumbs;
}

function getDescendantIds(
  folderId: string,
  byParent: Map<string | null, QuizFolder[]>
): Set<string> {
  const out = new Set<string>([folderId]);
  const stack = [folderId];
  while (stack.length > 0) {
    const cur = stack.pop()!;
    for (const child of byParent.get(cur) ?? []) {
      if (!out.has(child.id)) {
        out.add(child.id);
        stack.push(child.id);
      }
    }
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* Main component                                                     */
/* ------------------------------------------------------------------ */

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
  onGenerate,
  onImport,
}: QuizBankBrowserProps) {
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [prompt, setPrompt] = useState<PromptState | null>(null);
  const [promptValue, setPromptValue] = useState("");
  const [move, setMove] = useState<MoveState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    type: "folder" | "quiz";
    id: string;
    name: string;
  } | null>(null);

  const byId = useMemo(
    () => new Map(folders.map((f) => [f.id, f])),
    [folders]
  );
  const byParent = useMemo(() => buildChildrenMap(folders), [folders]);

  // Sanity: if current folder got deleted out from under us, fall back to root.
  useEffect(() => {
    if (currentId !== null && !byId.has(currentId)) setCurrentId(null);
  }, [currentId, byId]);

  const currentFolders = useMemo(() => {
    const list = byParent.get(currentId) ?? [];
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [byParent, currentId]);

  const currentQuizzes = useMemo(() => {
    return quizzes
      .filter((q) => (q.folder_id ?? null) === currentId)
      .sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
  }, [quizzes, currentId]);

  const crumbs = useMemo(
    () => getAncestors(currentId, byId),
    [currentId, byId]
  );

  const submitPrompt = () => {
    const name = promptValue.trim();
    if (!name || !prompt) return;
    if (prompt.mode === "new-folder") {
      onCreateFolder(prompt.parentId ?? null, name);
    } else if (prompt.mode === "rename-folder" && prompt.folderId) {
      onRenameFolder(prompt.folderId, name);
    }
    setPrompt(null);
    setPromptValue("");
  };

  const openNewFolder = (parentId: string | null = currentId) => {
    setPrompt({ mode: "new-folder", parentId });
    setPromptValue("");
  };

  const openRename = (folder: QuizFolder) => {
    setPrompt({
      mode: "rename-folder",
      folderId: folder.id,
      initial: folder.name,
    });
    setPromptValue(folder.name);
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    if (deleteTarget.type === "folder") onDeleteFolder(deleteTarget.id);
    else onDeleteQuiz(deleteTarget.id);
    setDeleteTarget(null);
  };

  const performMove = (targetId: string | null) => {
    if (!move) return;
    if (move.type === "folder") onMoveFolder(move.id, targetId);
    else onMoveQuiz(move.id, targetId);
    setMove(null);
  };

  const isEmpty = currentFolders.length === 0 && currentQuizzes.length === 0;

  return (
    <div className="space-y-4">
      {/* Toolbar: breadcrumb on the left, actions on the right */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumbs
          crumbs={crumbs}
          onGoTo={(id) => setCurrentId(id)}
        />
        <div className="flex items-center gap-2">
          <ViewToggle value={viewMode} onChange={setViewMode} />
          <NewMenu
            onNewFolder={() => openNewFolder()}
            onGenerate={onGenerate}
            onImport={onImport}
          />
        </div>
      </div>

      {/* Content */}
      {isEmpty ? (
        <EmptyState
          onNewFolder={() => openNewFolder()}
          onGenerate={onGenerate}
          onImport={onImport}
        />
      ) : (
        <div className="space-y-5">
          {currentFolders.length > 0 && (
            <SectionHeader label="Folders" count={currentFolders.length} />
          )}
          {currentFolders.length > 0 && (
            <div
              className={
                viewMode === "grid"
                  ? "grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
                  : "space-y-2"
              }
            >
              {currentFolders.map((f) => (
                <FolderCard
                  key={f.id}
                  folder={f}
                  childCount={
                    (byParent.get(f.id)?.length ?? 0) +
                    quizzes.filter((q) => q.folder_id === f.id).length
                  }
                  view={viewMode}
                  onOpen={() => setCurrentId(f.id)}
                  onRename={() => openRename(f)}
                  onMove={() =>
                    setMove({
                      type: "folder",
                      id: f.id,
                      currentParentId: f.parent_id,
                    })
                  }
                  onDelete={() =>
                    setDeleteTarget({
                      type: "folder",
                      id: f.id,
                      name: f.name,
                    })
                  }
                />
              ))}
            </div>
          )}

          {currentQuizzes.length > 0 && (
            <SectionHeader label="Quizzes" count={currentQuizzes.length} />
          )}
          {currentQuizzes.length > 0 && (
            <div
              className={
                viewMode === "grid"
                  ? "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
                  : "space-y-2"
              }
            >
              {currentQuizzes.map((q) => (
                <QuizCard
                  key={q.id}
                  quiz={q}
                  view={viewMode}
                  onStart={() => onStartSession(q.id)}
                  onMove={() =>
                    setMove({
                      type: "quiz",
                      id: q.id,
                      currentParentId: q.folder_id,
                    })
                  }
                  onDelete={() =>
                    setDeleteTarget({
                      type: "quiz",
                      id: q.id,
                      name: q.title,
                    })
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* New folder / rename dialog */}
      <Dialog
        open={prompt !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPrompt(null);
            setPromptValue("");
          }
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              {prompt?.mode === "new-folder" ? "New folder" : "Rename folder"}
            </DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            value={promptValue}
            onChange={(e) => setPromptValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitPrompt();
            }}
            placeholder="Folder name"
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setPrompt(null);
                setPromptValue("");
              }}
            >
              Cancel
            </Button>
            <Button onClick={submitPrompt} disabled={!promptValue.trim()}>
              {prompt?.mode === "new-folder" ? "Create" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Move dialog */}
      <MoveDialog
        open={move !== null}
        onOpenChange={(open) => !open && setMove(null)}
        folders={folders}
        byParent={byParent}
        disabledIds={
          move?.type === "folder"
            ? getDescendantIds(move.id, byParent)
            : new Set()
        }
        currentParentId={move?.currentParentId ?? null}
        onPick={performMove}
      />

      {/* Delete confirmation */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>
              Delete {deleteTarget?.type === "folder" ? "folder" : "quiz"}?
            </DialogTitle>
            <DialogDescription>
              {deleteTarget?.type === "folder"
                ? "Items inside will move to this folder's parent. The folder itself is removed."
                : "This removes the quiz and all its questions from the live bank."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sub-components                                                     */
/* ------------------------------------------------------------------ */

function Breadcrumbs({
  crumbs,
  onGoTo,
}: {
  crumbs: readonly QuizFolder[];
  onGoTo: (id: string | null) => void;
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1 text-sm text-[var(--color-text-muted)]"
    >
      <button
        type="button"
        onClick={() => onGoTo(null)}
        className="flex items-center gap-1 rounded-[var(--radius-sm)] px-1.5 py-1 font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        <Home className="size-4" />
        Question Bank
      </button>
      {crumbs.map((c, i) => (
        <span key={c.id} className="flex items-center gap-1">
          <ChevronRight className="size-3.5 shrink-0 text-[var(--color-text-muted)]" />
          <button
            type="button"
            onClick={() => onGoTo(c.id)}
            className={`max-w-[180px] truncate rounded-[var(--radius-sm)] px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-hover)] ${
              i === crumbs.length - 1
                ? "font-medium text-[var(--color-text)]"
                : ""
            }`}
          >
            {c.name}
          </button>
        </span>
      ))}
    </nav>
  );
}

function ViewToggle({
  value,
  onChange,
}: {
  value: ViewMode;
  onChange: (v: ViewMode) => void;
}) {
  return (
    <div className="inline-flex rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-0.5">
      <button
        type="button"
        onClick={() => onChange("grid")}
        aria-pressed={value === "grid"}
        aria-label="Grid view"
        className={`flex size-8 items-center justify-center rounded-[var(--radius-sm)] transition-colors ${
          value === "grid"
            ? "bg-[var(--color-surface-hover)] text-[var(--color-text)]"
            : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        }`}
      >
        <LayoutGrid className="size-4" />
      </button>
      <button
        type="button"
        onClick={() => onChange("list")}
        aria-pressed={value === "list"}
        aria-label="List view"
        className={`flex size-8 items-center justify-center rounded-[var(--radius-sm)] transition-colors ${
          value === "list"
            ? "bg-[var(--color-surface-hover)] text-[var(--color-text)]"
            : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        }`}
      >
        <Rows3 className="size-4" />
      </button>
    </div>
  );
}

function NewMenu({
  onNewFolder,
  onGenerate,
  onImport,
}: {
  onNewFolder: () => void;
  onGenerate: () => void;
  onImport: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button size="sm" />}>
        <Plus className="size-4" />
        New
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuItem onClick={onNewFolder}>
          <FolderPlus className="size-4" />
          New folder
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onGenerate}>
          <Sparkles className="size-4" />
          Generate quiz
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onImport}>
          <Download className="size-4" />
          Import from quiz
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center gap-2 px-1 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
      <span>{label}</span>
      <span className="text-[var(--color-text-muted)]">· {count}</span>
    </div>
  );
}

function FolderCard({
  folder,
  childCount,
  view,
  onOpen,
  onRename,
  onMove,
  onDelete,
}: {
  folder: QuizFolder;
  childCount: number;
  view: ViewMode;
  onOpen: () => void;
  onRename: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  const hue = hueFor(folder.id);
  if (view === "list") {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onOpen}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpen();
          }
        }}
        className="group flex cursor-pointer items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 transition-all hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-sm)]"
      >
        <span
          className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
          style={{ backgroundColor: hue.bg, color: hue.fg }}
        >
          <Folder className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-[var(--color-text)]">
            {folder.name}
          </p>
          <p className="text-xs text-[var(--color-text-muted)]">
            {childCount} {childCount === 1 ? "item" : "items"}
          </p>
        </div>
        <ItemMenu
          onRename={onRename}
          onMove={onMove}
          onDelete={onDelete}
          renameLabel="Rename"
        />
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="group relative flex aspect-[4/3] cursor-pointer flex-col justify-between overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)] active:translate-y-0 active:shadow-[var(--shadow-sm)]"
      style={{ backgroundColor: hue.bg }}
    >
      <div className="flex items-start justify-between">
        <Folder className="size-8" style={{ color: hue.fg }} />
        <div
          className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
          onClick={(e) => e.stopPropagation()}
        >
          <ItemMenu
            onRename={onRename}
            onMove={onMove}
            onDelete={onDelete}
            renameLabel="Rename"
          />
        </div>
      </div>
      <div className="min-w-0">
        <p
          className="truncate text-sm font-semibold"
          style={{ color: hue.fg }}
        >
          {folder.name}
        </p>
        <p className="mt-0.5 text-xs" style={{ color: hue.fg, opacity: 0.75 }}>
          {childCount} {childCount === 1 ? "item" : "items"}
        </p>
      </div>
    </div>
  );
}

function QuizCard({
  quiz,
  view,
  onStart,
  onMove,
  onDelete,
}: {
  quiz: QuizResponse;
  view: ViewMode;
  onStart: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  if (view === "list") {
    return (
      <div className="group flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5 transition-all hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-sm)]">
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
        <Button size="sm" variant="outline" onClick={onStart}>
          Start
        </Button>
        <ItemMenu
          onMove={onMove}
          onDelete={onDelete}
          renameLabel={null}
        />
      </div>
    );
  }

  return (
    <div className="group flex flex-col gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
      <div className="flex items-start justify-between">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
          <FileQuestion className="size-5" />
        </span>
        <div className="opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          <ItemMenu
            onMove={onMove}
            onDelete={onDelete}
            renameLabel={null}
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
      <Button size="sm" className="w-full" onClick={onStart}>
        Start Session
      </Button>
    </div>
  );
}

function ItemMenu({
  onRename,
  onMove,
  onDelete,
  renameLabel,
}: {
  onRename?: () => void;
  onMove: () => void;
  onDelete: () => void;
  renameLabel: string | null;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            size="sm"
            variant="ghost"
            aria-label="More actions"
            onClick={(e) => e.stopPropagation()}
            className="size-8 shrink-0 p-0"
          />
        }
      >
        <MoreHorizontal className="size-4" />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-44"
        onClick={(e) => e.stopPropagation()}
      >
        {renameLabel && onRename && (
          <DropdownMenuItem onClick={onRename}>
            <Pencil className="size-4" />
            {renameLabel}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onClick={onMove}>
          <ArrowRight className="size-4" />
          Move to…
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onDelete} variant="destructive">
          <Trash2 className="size-4" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function EmptyState({
  onNewFolder,
  onGenerate,
  onImport,
}: {
  onNewFolder: () => void;
  onGenerate: () => void;
  onImport: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
        <Folder className="size-6 text-[var(--color-primary)]" />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--color-text)]">
          Nothing here yet
        </p>
        <p className="mt-1 max-w-xs text-xs text-[var(--color-text-muted)]">
          Add a folder to organize, or create your first live quiz.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="outline" size="sm" onClick={onNewFolder}>
          <FolderPlus className="size-4" />
          New Folder
        </Button>
        <Button variant="outline" size="sm" onClick={onImport}>
          <Download className="size-4" />
          Import
        </Button>
        <Button size="sm" onClick={onGenerate}>
          <Sparkles className="size-4" />
          Generate
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Move dialog — mini tree picker                                     */
/* ------------------------------------------------------------------ */

function MoveDialog({
  open,
  onOpenChange,
  folders,
  byParent,
  disabledIds,
  currentParentId,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  folders: readonly QuizFolder[];
  byParent: Map<string | null, QuizFolder[]>;
  disabledIds: Set<string>;
  currentParentId: string | null;
  onPick: (folderId: string | null) => void;
}) {
  const [pick, setPick] = useState<string | null>(currentParentId);

  useEffect(() => {
    if (open) setPick(currentParentId);
  }, [open, currentParentId]);

  const rows = useMemo(() => {
    const out: { folder: QuizFolder | null; depth: number }[] = [];
    out.push({ folder: null, depth: 0 });
    const walk = (parentId: string | null, depth: number) => {
      const children = [...(byParent.get(parentId) ?? [])].sort((a, b) =>
        a.name.localeCompare(b.name)
      );
      for (const c of children) {
        out.push({ folder: c, depth });
        walk(c.id, depth + 1);
      }
    };
    walk(null, 1);
    return out;
  }, [byParent, folders]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Move to…</DialogTitle>
          <DialogDescription>
            Choose a destination folder. Pick the home icon for Ungrouped.
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-[50vh] overflow-y-auto rounded-[var(--radius-md)] border border-[var(--color-border)]">
          {rows.map((row) => {
            const id = row.folder?.id ?? null;
            const disabled = id !== null && disabledIds.has(id);
            const selected = pick === id;
            return (
              <button
                key={id ?? "__root__"}
                type="button"
                disabled={disabled}
                onClick={() => setPick(id)}
                className={`flex w-full items-center gap-2 border-b border-[var(--color-border)] px-3 py-2 text-left text-sm last:border-b-0 transition-colors ${
                  selected
                    ? "bg-[var(--color-primary-light)] text-[var(--color-text)]"
                    : "hover:bg-[var(--color-surface-hover)]"
                } ${disabled ? "cursor-not-allowed opacity-40" : ""}`}
                style={{ paddingLeft: `${12 + row.depth * 18}px` }}
              >
                {row.folder === null ? (
                  <Home className="size-4 text-[var(--color-text-muted)]" />
                ) : (
                  <Folder
                    className="size-4"
                    style={{ color: hueFor(row.folder.id).fg }}
                  />
                )}
                <span className="flex-1 truncate text-[var(--color-text)]">
                  {row.folder?.name ?? "Ungrouped"}
                </span>
                {selected && <Check className="size-4 text-[var(--color-primary)]" />}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => onPick(pick)} disabled={pick === currentParentId}>
            Move here
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
