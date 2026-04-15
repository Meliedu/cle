"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Folder,
  FolderPlus,
  MoreHorizontal,
  ChevronRight,
  Home,
  Pencil,
  Trash2,
  ArrowRight,
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

/* ------------------------------------------------------------------ */
/* Public types                                                       */
/* ------------------------------------------------------------------ */

export interface FolderLike {
  readonly id: string;
  readonly name: string;
  readonly parent_id: string | null;
  readonly created_at: string;
}

export interface ItemLike {
  readonly id: string;
  readonly folder_id: string | null;
}

export type ViewMode = "grid" | "list";

export interface NewMenuAction {
  readonly key: string;
  readonly label: string;
  readonly icon: ReactNode;
  readonly onClick: () => void;
}

export interface RenderItemCtx {
  readonly view: ViewMode;
  readonly onMove: () => void;
}

export interface FolderBrowserProps<TItem extends ItemLike> {
  readonly folders: readonly FolderLike[];
  readonly items: readonly TItem[];
  readonly itemSectionLabel: string;
  readonly emptyTitle?: string;
  readonly emptyBody?: string;
  readonly newMenuActions?: readonly NewMenuAction[];
  readonly renderItem: (item: TItem, ctx: RenderItemCtx) => ReactNode;
  readonly onCreateFolder: (parentId: string | null, name: string) => void;
  readonly onRenameFolder: (folderId: string, name: string) => void;
  readonly onDeleteFolder: (folderId: string) => void;
  readonly onMoveFolder: (folderId: string, parentId: string | null) => void;
  readonly onMoveItem: (itemId: string, folderId: string | null) => void;
  readonly sortItems?: (a: TItem, b: TItem) => number;
  /** Number of items+subfolders beneath a folder. If omitted, computed internally */
  readonly childCountOf?: (folderId: string) => number;
  /** Pluralized noun shown inside folder tiles, e.g. "items" or "sets" */
  readonly itemCountNoun?: { singular: string; plural: string };
}

/* ------------------------------------------------------------------ */
/* Internal state helpers                                             */
/* ------------------------------------------------------------------ */

interface PromptState {
  readonly mode: "new-folder" | "rename-folder";
  readonly folderId?: string;
  readonly parentId?: string | null;
}

interface MoveState {
  readonly type: "folder" | "item";
  readonly id: string;
  readonly currentParentId: string | null;
}

/* ------------------------------------------------------------------ */
/* Visual tokens                                                      */
/* ------------------------------------------------------------------ */

const FOLDER_HUES = [
  { bg: "oklch(94% 0.03 250)", fg: "oklch(45% 0.15 250)" },
  { bg: "oklch(94% 0.04 155)", fg: "oklch(45% 0.15 155)" },
  { bg: "oklch(94% 0.04 75)", fg: "oklch(45% 0.15 75)" },
  { bg: "oklch(94% 0.04 25)", fg: "oklch(45% 0.18 25)" },
  { bg: "oklch(94% 0.04 300)", fg: "oklch(45% 0.18 300)" },
  { bg: "oklch(94% 0.04 200)", fg: "oklch(45% 0.15 200)" },
];

export function folderHueFor(id: string) {
  let h = 0;
  for (let i = 0; i < id.length; i += 1) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return FOLDER_HUES[h % FOLDER_HUES.length];
}

/* ------------------------------------------------------------------ */
/* Tree helpers                                                       */
/* ------------------------------------------------------------------ */

function buildChildrenMap(folders: readonly FolderLike[]) {
  const byParent = new Map<string | null, FolderLike[]>();
  for (const f of folders) {
    const bucket = byParent.get(f.parent_id) ?? [];
    bucket.push(f);
    byParent.set(f.parent_id, bucket);
  }
  return byParent;
}

function getAncestors(
  folderId: string | null,
  byId: Map<string, FolderLike>
): FolderLike[] {
  const crumbs: FolderLike[] = [];
  let cur = folderId ? byId.get(folderId) : null;
  while (cur) {
    crumbs.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) ?? null : null;
  }
  return crumbs;
}

function getDescendantIds(
  folderId: string,
  byParent: Map<string | null, FolderLike[]>
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

export function FolderBrowser<TItem extends ItemLike>({
  folders,
  items,
  itemSectionLabel,
  emptyTitle = "Nothing here yet",
  emptyBody = "Add a folder to organize, or create your first item.",
  newMenuActions = [],
  renderItem,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onMoveFolder,
  onMoveItem,
  sortItems,
  childCountOf,
  itemCountNoun = { singular: "item", plural: "items" },
}: FolderBrowserProps<TItem>) {
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [prompt, setPrompt] = useState<PromptState | null>(null);
  const [promptValue, setPromptValue] = useState("");
  const [move, setMove] = useState<MoveState | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    type: "folder";
    id: string;
    name: string;
  } | null>(null);

  const byId = useMemo(
    () => new Map(folders.map((f) => [f.id, f])),
    [folders]
  );
  const byParent = useMemo(() => buildChildrenMap(folders), [folders]);

  useEffect(() => {
    if (currentId !== null && !byId.has(currentId)) setCurrentId(null);
  }, [currentId, byId]);

  const currentFolders = useMemo(() => {
    const list = byParent.get(currentId) ?? [];
    return [...list].sort((a, b) => a.name.localeCompare(b.name));
  }, [byParent, currentId]);

  const currentItems = useMemo(() => {
    const filtered = items.filter(
      (it) => (it.folder_id ?? null) === currentId
    );
    return sortItems ? [...filtered].sort(sortItems) : filtered;
  }, [items, currentId, sortItems]);

  const crumbs = useMemo(
    () => getAncestors(currentId, byId),
    [currentId, byId]
  );

  const computeChildCount = (folderId: string): number => {
    if (childCountOf) return childCountOf(folderId);
    return (
      (byParent.get(folderId)?.length ?? 0) +
      items.filter((it) => it.folder_id === folderId).length
    );
  };

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

  const openRename = (folder: FolderLike) => {
    setPrompt({ mode: "rename-folder", folderId: folder.id });
    setPromptValue(folder.name);
  };

  const performMove = (targetId: string | null) => {
    if (!move) return;
    if (move.type === "folder") onMoveFolder(move.id, targetId);
    else onMoveItem(move.id, targetId);
    setMove(null);
  };

  const isEmpty = currentFolders.length === 0 && currentItems.length === 0;

  const allActions: NewMenuAction[] = [
    {
      key: "new-folder",
      label: "New folder",
      icon: <FolderPlus className="size-4" />,
      onClick: () => openNewFolder(),
    },
    ...newMenuActions,
  ];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Breadcrumbs crumbs={crumbs} onGoTo={(id) => setCurrentId(id)} />
        <div className="flex items-center gap-2">
          <ViewToggle value={viewMode} onChange={setViewMode} />
          <NewMenu actions={allActions} />
        </div>
      </div>

      {/* Content */}
      {isEmpty ? (
        <EmptyState
          title={emptyTitle}
          body={emptyBody}
          actions={allActions}
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
                  ? "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5"
                  : "space-y-2"
              }
            >
              {currentFolders.map((f) => (
                <FolderCard
                  key={f.id}
                  folder={f}
                  childCount={computeChildCount(f.id)}
                  itemCountNoun={itemCountNoun}
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
                    setDeleteTarget({ type: "folder", id: f.id, name: f.name })
                  }
                />
              ))}
            </div>
          )}

          {currentItems.length > 0 && (
            <SectionHeader
              label={itemSectionLabel}
              count={currentItems.length}
            />
          )}
          {currentItems.length > 0 && (
            <div
              className={
                viewMode === "grid"
                  ? "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
                  : "space-y-2"
              }
            >
              {currentItems.map((it) => (
                <div key={it.id}>
                  {renderItem(it, {
                    view: viewMode,
                    onMove: () =>
                      setMove({
                        type: "item",
                        id: it.id,
                        currentParentId: it.folder_id,
                      }),
                  })}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* New / rename dialog */}
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

      {/* Delete folder confirmation */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete folder?</DialogTitle>
            <DialogDescription>
              Items inside will move to this folder's parent. The folder itself
              is removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                if (deleteTarget) onDeleteFolder(deleteTarget.id);
                setDeleteTarget(null);
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Reusable item-menu shown by callers inside renderItem              */
/* ------------------------------------------------------------------ */

export interface ItemActionsMenuProps {
  readonly onMove: () => void;
  readonly onDelete?: () => void;
  readonly extra?: ReactNode;
}

export function ItemActionsMenu({ onMove, onDelete, extra }: ItemActionsMenuProps) {
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
        <DropdownMenuItem onClick={onMove}>
          <ArrowRight className="size-4" />
          Move to…
        </DropdownMenuItem>
        {extra}
        {onDelete && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onDelete} variant="destructive">
              <Trash2 className="size-4" />
              Delete
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* ------------------------------------------------------------------ */
/* Internal sub-components                                            */
/* ------------------------------------------------------------------ */

function Breadcrumbs({
  crumbs,
  onGoTo,
}: {
  crumbs: readonly FolderLike[];
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
        Home
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

function NewMenu({ actions }: { actions: readonly NewMenuAction[] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button size="sm" />}>
        <Plus className="size-4" />
        New
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {actions.map((a, i) => (
          <DropdownMenuItem key={a.key} onClick={a.onClick}>
            {a.icon}
            {a.label}
            {i === 0 && actions.length > 1 && <DropdownMenuSeparator />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center gap-2 px-1 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
      <span>{label}</span>
      <span>· {count}</span>
    </div>
  );
}

function FolderCard({
  folder,
  childCount,
  itemCountNoun,
  view,
  onOpen,
  onRename,
  onMove,
  onDelete,
}: {
  folder: FolderLike;
  childCount: number;
  itemCountNoun: { singular: string; plural: string };
  view: ViewMode;
  onOpen: () => void;
  onRename: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  const hue = folderHueFor(folder.id);
  const label =
    childCount === 1 ? itemCountNoun.singular : itemCountNoun.plural;

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
            {childCount} {label}
          </p>
        </div>
        <div onClick={(e) => e.stopPropagation()}>
          <FolderMenu
            onRename={onRename}
            onMove={onMove}
            onDelete={onDelete}
          />
        </div>
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
      className="group relative flex cursor-pointer flex-col gap-2 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] px-3 py-3.5 transition-all hover:-translate-y-0.5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)] active:translate-y-0 active:shadow-[var(--shadow-sm)]"
      style={{ backgroundColor: hue.bg }}
    >
      <div className="flex items-start justify-between">
        <Folder className="size-6" style={{ color: hue.fg }} />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className="truncate text-sm font-semibold"
          style={{ color: hue.fg }}
        >
          {folder.name}
        </p>
        <p className="text-xs" style={{ color: hue.fg, opacity: 0.75 }}>
          {childCount} {label}
        </p>
      </div>
      <div
        className="absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100"
        onClick={(e) => e.stopPropagation()}
      >
        <FolderMenu
          onRename={onRename}
          onMove={onMove}
          onDelete={onDelete}
        />
      </div>
    </div>
  );
}

function FolderMenu({
  onRename,
  onMove,
  onDelete,
}: {
  onRename: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            size="sm"
            variant="ghost"
            aria-label="Folder actions"
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
        <DropdownMenuItem onClick={onRename}>
          <Pencil className="size-4" />
          Rename
        </DropdownMenuItem>
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
  title,
  body,
  actions,
}: {
  title: string;
  body: string;
  actions: readonly NewMenuAction[];
}) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-6 py-12 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
        <Folder className="size-6 text-[var(--color-primary)]" />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--color-text)]">{title}</p>
        <p className="mt-1 max-w-xs text-xs text-[var(--color-text-muted)]">
          {body}
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {actions.map((a) => (
          <Button
            key={a.key}
            variant={a.key === "new-folder" ? "outline" : undefined}
            size="sm"
            onClick={a.onClick}
          >
            {a.icon}
            {a.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Move dialog                                                        */
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
  folders: readonly FolderLike[];
  byParent: Map<string | null, FolderLike[]>;
  disabledIds: Set<string>;
  currentParentId: string | null;
  onPick: (folderId: string | null) => void;
}) {
  const [pick, setPick] = useState<string | null>(currentParentId);

  useEffect(() => {
    if (open) setPick(currentParentId);
  }, [open, currentParentId]);

  const rows = useMemo(() => {
    const out: { folder: FolderLike | null; depth: number }[] = [];
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [byParent, folders]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Move to…</DialogTitle>
          <DialogDescription>
            Choose a destination folder. Pick the home icon to move to the top
            level.
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
                    style={{ color: folderHueFor(row.folder.id).fg }}
                  />
                )}
                <span className="flex-1 truncate text-[var(--color-text)]">
                  {row.folder?.name ?? "Top level"}
                </span>
                {selected && (
                  <Check className="size-4 text-[var(--color-primary)]" />
                )}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => onPick(pick)}
            disabled={pick === currentParentId}
          >
            Move here
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
