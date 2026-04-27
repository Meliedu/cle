"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  Globe,
  GlobeLock,
  Languages,
  Loader2,
  Mic,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { DifficultyBadge } from "@/components/ui/difficulty-badge";
import {
  useAddPronunciationItem,
  useDeletePronunciationItem,
  usePronunciationSet,
  usePublishPronunciationSet,
  useRegeneratePronunciationItem,
  useUpdatePronunciationItem,
  type PronunciationItemResponse,
} from "@/hooks/use-pronunciation-sets";
import { PronunciationItemEditor } from "./pronunciation-item-editor";

interface PronunciationPreviewProps {
  readonly setId: string;
  readonly courseId: string;
}

type EditorState =
  | { readonly mode: "closed" }
  | { readonly mode: "create" }
  | { readonly mode: "edit"; readonly item: PronunciationItemResponse };

export function PronunciationPreview({
  setId,
  courseId,
}: PronunciationPreviewProps) {
  const router = useRouter();
  const { data: pronSet, isLoading, error } = usePronunciationSet(setId);
  const publishMutation = usePublishPronunciationSet(courseId);
  const addItem = useAddPronunciationItem(courseId, setId);
  const updateItem = useUpdatePronunciationItem(courseId, setId);
  const deleteItem = useDeletePronunciationItem(courseId, setId);
  const regenerateItem = useRegeneratePronunciationItem(courseId, setId);

  const [editor, setEditor] = useState<EditorState>({ mode: "closed" });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !pronSet) {
    return (
      <Card className="mx-auto max-w-3xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error
              ? error.message
              : "Failed to load pronunciation set"}
          </p>
        </CardContent>
      </Card>
    );
  }

  const editorBusy = addItem.isPending || updateItem.isPending;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                router.push(`/dashboard/courses/${courseId}/pronunciation`)
              }
            >
              <ArrowLeft className="size-4" />
            </Button>
            <h1 className="text-xl font-bold text-[var(--color-text)]">
              {pronSet.title}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 pl-9">
            <Badge
              variant="outline"
              className={
                pronSet.is_published
                  ? "border-[var(--color-success)] text-[var(--color-success)]"
                  : "border-[var(--color-warning)] text-[var(--color-warning)]"
              }
            >
              {pronSet.is_published ? "Published" : "Draft"}
            </Badge>
            <Badge variant="outline">
              <Mic className="size-3" />
              {pronSet.items.length} items
            </Badge>
            <Badge variant="outline">
              <Languages className="size-3" />
              {pronSet.language}
            </Badge>
            <DifficultyBadge value={pronSet.difficulty} size="sm" />
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => publishMutation.mutate(pronSet.id)}
            disabled={publishMutation.isPending}
          >
            {pronSet.is_published ? (
              <>
                <GlobeLock className="size-4" />
                Unpublish
              </>
            ) : (
              <>
                <Globe className="size-4" />
                Publish
              </>
            )}
          </Button>
          <Button
            size="sm"
            onClick={() => setEditor({ mode: "create" })}
          >
            <Plus className="size-4" />
            Add item
          </Button>
        </div>
      </div>

      <Separator />

      {/* Items list */}
      <div className="space-y-3">
        {pronSet.items.map((item, idx) => {
          const isRegenerating =
            regenerateItem.isPending && regenerateItem.variables === item.id;
          const isDeleting =
            deleteItem.isPending && deleteItem.variables === item.id;
          return (
            <Card key={item.id}>
              <CardContent className="space-y-3">
                <div className="flex items-start gap-3">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-xs font-bold text-[var(--color-primary)]">
                    {idx + 1}
                  </span>
                  <div className="flex-1 space-y-2">
                    <div className="-mt-1 flex flex-wrap items-center justify-end gap-2">
                      <Badge variant="outline" className="capitalize">
                        {item.item_type}
                      </Badge>
                      <DifficultyBadge value={item.difficulty} size="sm" />
                    </div>
                    <p className="text-base font-medium text-[var(--color-text)]">
                      {item.text}
                    </p>
                    {item.phonetic && (
                      <p className="font-mono text-sm text-[var(--color-text-muted)]">
                        {item.phonetic}
                      </p>
                    )}
                    {item.translation && (
                      <div>
                        <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                          Translation
                        </p>
                        <p className="text-sm text-[var(--color-text-secondary)]">
                          {item.translation}
                        </p>
                      </div>
                    )}
                    {item.tips && (
                      <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface-hover)] p-2">
                        <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                          Tip
                        </p>
                        <p className="text-sm text-[var(--color-text)]">
                          {item.tips}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Per-item actions */}
                <div className="ml-10 flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditor({ mode: "edit", item })}
                    disabled={isRegenerating || isDeleting}
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
                  >
                    <Pencil className="size-3.5" />
                    Edit
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => regenerateItem.mutate(item.id)}
                    disabled={isRegenerating || isDeleting}
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-primary)]"
                  >
                    {isRegenerating ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                    {isRegenerating ? "Regenerating..." : "Regenerate"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteItem.mutate(item.id)}
                    disabled={
                      isDeleting ||
                      isRegenerating ||
                      pronSet.items.length <= 1
                    }
                    className="text-[var(--color-text-muted)] hover:text-[var(--color-error)]"
                  >
                    <Trash2 className="size-3.5" />
                    Remove
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <PronunciationItemEditor
        mode={editor.mode === "edit" ? "edit" : "create"}
        open={editor.mode !== "closed"}
        initial={editor.mode === "edit" ? editor.item : null}
        isSaving={editorBusy}
        onCancel={() => setEditor({ mode: "closed" })}
        onSubmit={(draft) => {
          if (editor.mode === "edit") {
            updateItem.mutate(
              {
                item_id: editor.item.id,
                text: draft.text,
                item_type: draft.item_type,
                phonetic: draft.phonetic.trim() || null,
                translation: draft.translation.trim() || null,
                tips: draft.tips.trim() || null,
                difficulty: draft.difficulty,
              },
              { onSuccess: () => setEditor({ mode: "closed" }) }
            );
          } else {
            addItem.mutate(
              {
                text: draft.text,
                item_type: draft.item_type,
                phonetic: draft.phonetic.trim() || null,
                translation: draft.translation.trim() || null,
                tips: draft.tips.trim() || null,
                difficulty: draft.difficulty,
              },
              { onSuccess: () => setEditor({ mode: "closed" }) }
            );
          }
        }}
      />

    </div>
  );
}
