"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { RemovedReason } from "@/hooks/use-checkpoints";

const REMOVE_REASONS: readonly RemovedReason[] = [
  "not_needed",
  "duplicate",
  "not_covered",
  "other",
];

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";

interface RemoveCardDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The prompt of the card being removed, echoed for confirmation. */
  readonly cardPrompt: string;
  readonly pending?: boolean;
  /** Confirm removal with the chosen reason + an optional free-text note. */
  readonly onConfirm: (reason: RemovedReason, note: string) => void;
}

/**
 * T042 — remove-review-card reason modal. Before a review-point card is
 * soft-removed we capture a categorized `removed_reason` (§4.2 audit) plus an
 * optional note, so the removal is explainable later. The final_comments card is
 * fixed and never reaches this dialog (the studio hides its remove affordance).
 */
export function RemoveCardDialog({
  open,
  onOpenChange,
  cardPrompt,
  pending = false,
  onConfirm,
}: RemoveCardDialogProps) {
  const t = useTranslations("teacher.studio.removeDialog");
  const [reason, setReason] = useState<RemovedReason>("not_needed");
  const [note, setNote] = useState("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <p className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3 py-2.5 text-[13px] leading-relaxed text-[var(--color-text)]">
            {cardPrompt}
          </p>

          <div className="space-y-1.5">
            <label
              htmlFor="remove-reason"
              className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("reasonLabel")}
            </label>
            <select
              id="remove-reason"
              className={SELECT_CLASS}
              value={reason}
              onChange={(e) => setReason(e.target.value as RemovedReason)}
            >
              {REMOVE_REASONS.map((r) => (
                <option key={r} value={r}>
                  {t(`reason.${r}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="remove-note"
              className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("noteLabel")}
            </label>
            <Textarea
              id="remove-note"
              rows={2}
              value={note}
              placeholder={t("notePlaceholder")}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={pending}
            onClick={() => onConfirm(reason, note.trim())}
          >
            {pending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Trash2 aria-hidden="true" />
            )}
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
