"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import {
  useAssignMaterial,
  useDeleteDocument,
} from "@/hooks/use-documents";
import type { DocumentResponse } from "@/hooks/use-documents";

type RemoveMode = "unassign" | "delete";

interface RemoveMaterialDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly courseId: string;
  readonly doc: DocumentResponse;
  /** Called after a successful delete so the caller can clear its selection. */
  readonly onRemoved: () => void;
}

/**
 * T057/T058 — remove-material confirmation. When the file is assigned to a
 * session the teacher can either move it back to "Unassigned" (keeps it in the
 * library, via `useAssignMaterial(null)`) or delete it from the course
 * entirely (`useDeleteDocument`, the existing soft-delete). An unassigned file
 * offers delete only. Delete is destructive, so it is the danger-styled,
 * non-default choice with an explicit warning.
 */
export function RemoveMaterialDialog({
  open,
  onOpenChange,
  courseId,
  doc,
  onRemoved,
}: RemoveMaterialDialogProps) {
  const t = useTranslations("teacher.materials.remove");
  const assign = useAssignMaterial(courseId);
  const del = useDeleteDocument(courseId);

  const canUnassign = doc.meeting_id != null;
  const [mode, setMode] = useState<RemoveMode>(
    canUnassign ? "unassign" : "delete"
  );

  const pending = assign.isPending || del.isPending;

  const handleConfirm = async () => {
    if (mode === "unassign") {
      await assign.mutateAsync({ documentId: doc.id, meeting_id: null });
      onOpenChange(false);
    } else {
      await del.mutateAsync(doc.id);
      onOpenChange(false);
      onRemoved();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {t("subtitle", { name: doc.filename })}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          {canUnassign ? (
            <ModeOption
              title={t("optionUnassignTitle")}
              body={t("optionUnassignBody")}
              value="unassign"
              checked={mode === "unassign"}
              onSelect={setMode}
            />
          ) : null}
          <ModeOption
            title={t("optionDeleteTitle")}
            body={t("optionDeleteBody")}
            value="delete"
            danger
            checked={mode === "delete"}
            onSelect={setMode}
          />
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
            variant={mode === "delete" ? "destructive" : "default"}
            disabled={pending}
            onClick={handleConfirm}
            data-icon="inline-start"
          >
            {pending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Trash2 aria-hidden="true" />
            )}
            {mode === "delete" ? t("confirmDelete") : t("confirmUnassign")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ModeOptionProps {
  readonly title: string;
  readonly body: string;
  readonly value: RemoveMode;
  readonly checked: boolean;
  readonly danger?: boolean;
  readonly onSelect: (mode: RemoveMode) => void;
}

function ModeOption({
  title,
  body,
  value,
  checked,
  danger = false,
  onSelect,
}: ModeOptionProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer gap-2.5 rounded-[var(--radius-md)] border px-3 py-2.5 transition-colors duration-[var(--duration-fast)]",
        checked
          ? danger
            ? "border-[var(--color-error)]/50 bg-[var(--color-error-light)]"
            : "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
          : "border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <input
        type="radio"
        name="remove-mode"
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
        className={cn(
          "mt-0.5 size-3.5 shrink-0",
          danger
            ? "accent-[var(--color-error)]"
            : "accent-[var(--color-primary)]"
        )}
      />
      <span className="space-y-0.5">
        <span className="block text-[13px] font-medium text-[var(--color-text)]">
          {title}
        </span>
        <span className="block text-[12px] leading-relaxed text-[var(--color-text-muted)]">
          {body}
        </span>
      </span>
    </label>
  );
}
