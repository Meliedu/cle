"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Pencil, RotateCcw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { setupErrorCode } from "@/hooks/use-setup";
import {
  useUpdateCheckpointCard,
  type CheckpointCard,
  type RemovedReason,
} from "@/hooks/use-checkpoints";

import { RemoveCardDialog } from "./remove-card-dialog";

interface CheckpointCardEditorProps {
  readonly courseId: string;
  readonly checkpointId: string;
  readonly card: CheckpointCard;
  readonly position: number;
  /** When false, the checkpoint is past draft and cards are read-only. */
  readonly editable: boolean;
  readonly onError: (message: string | null) => void;
}

/**
 * T041 — review-point card editor. A single studio card row: view mode shows the
 * prompt + kind, edit mode swaps in a textarea over `useUpdateCheckpointCard`,
 * and the remove affordance opens the reason modal (T042). The fixed
 * final_comments card is editable but never removable (`FINAL_CARD_FIXED`), and
 * a soft-removed card renders muted with a restore action. Once the checkpoint
 * leaves draft (`editable=false`) the row is read-only — the backend refuses
 * card writes with `REVIEW_REQUIRED`.
 */
export function CheckpointCardEditor({
  courseId,
  checkpointId,
  card,
  position,
  editable,
  onError,
}: CheckpointCardEditorProps) {
  const t = useTranslations("teacher.studio");
  const update = useUpdateCheckpointCard(courseId, checkpointId);
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [prompt, setPrompt] = useState(card.prompt);
  const [removeOpen, setRemoveOpen] = useState(false);

  const isFinal = card.kind === "final_comments";

  const saveEdit = useCallback(async () => {
    onError(null);
    try {
      await update.mutateAsync({ cardId: card.id, prompt: prompt.trim() });
      setMode("view");
    } catch (error) {
      onError(t(`errors.${setupErrorCode(error) ?? "generic"}`));
    }
  }, [update, card.id, prompt, onError, t]);

  const confirmRemove = useCallback(
    async (reason: RemovedReason, note: string) => {
      onError(null);
      try {
        await update.mutateAsync({
          cardId: card.id,
          removed: true,
          removedReason: reason,
          removedNote: note || null,
        });
        setRemoveOpen(false);
      } catch (error) {
        onError(t(`errors.${setupErrorCode(error) ?? "generic"}`));
      }
    },
    [update, card.id, onError, t]
  );

  const restore = useCallback(async () => {
    onError(null);
    try {
      await update.mutateAsync({ cardId: card.id, removed: false });
    } catch (error) {
      onError(t(`errors.${setupErrorCode(error) ?? "generic"}`));
    }
  }, [update, card.id, onError, t]);

  if (card.removed) {
    return (
      <li className="flex items-start gap-3 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] bg-transparent p-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-surface-hover)] text-[12px] font-semibold text-[var(--color-text-muted)]">
          {position}
        </span>
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[13px] leading-relaxed text-[var(--color-text-muted)] line-through">
            {card.prompt}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary">
              {t(`removed.${card.removed_reason ?? "other"}`)}
            </Badge>
            {editable ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={update.isPending}
                onClick={() => void restore()}
              >
                <RotateCcw aria-hidden="true" />
                {t("restore")}
              </Button>
            ) : null}
          </div>
        </div>
      </li>
    );
  }

  return (
    <li className="flex gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-primary-light)] text-[12px] font-semibold text-[var(--color-primary-hover)]">
        {position}
      </span>

      <div className="min-w-0 flex-1 space-y-2">
        {mode === "edit" ? (
          <div className="space-y-2">
            <Textarea
              aria-label={t("promptLabel", { position })}
              rows={2}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={update.isPending || !prompt.trim()}
                onClick={() => void saveEdit()}
              >
                {update.isPending ? (
                  <Loader2 aria-hidden="true" className="animate-spin" />
                ) : null}
                {t("save")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setPrompt(card.prompt);
                  setMode("view");
                }}
              >
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-[13px] leading-relaxed text-[var(--color-text)]">
              {card.prompt}
            </p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline">
                {isFinal ? t("kind.final_comments") : t("kind.review_point")}
              </Badge>
              {editable ? (
                <>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setPrompt(card.prompt);
                      setMode("edit");
                    }}
                  >
                    <Pencil aria-hidden="true" />
                    {t("edit")}
                  </Button>
                  {isFinal ? (
                    <span className="inline-flex items-center gap-1 text-[12px] text-[var(--color-text-muted)]">
                      {t("fixed")}
                    </span>
                  ) : (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="text-[var(--color-error)]"
                      onClick={() => setRemoveOpen(true)}
                    >
                      <Trash2 aria-hidden="true" />
                      {t("remove")}
                    </Button>
                  )}
                </>
              ) : null}
            </div>
          </>
        )}
      </div>

      {!isFinal ? (
        <RemoveCardDialog
          open={removeOpen}
          onOpenChange={setRemoveOpen}
          cardPrompt={card.prompt}
          pending={update.isPending}
          onConfirm={(reason, note) => void confirmRemove(reason, note)}
        />
      ) : null}
    </li>
  );
}
