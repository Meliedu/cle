"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
import { useMeetings } from "@/hooks/use-meetings";
import { useAssignMaterial } from "@/hooks/use-documents";
import type { DocumentResponse } from "@/hooks/use-documents";

const UNASSIGNED_VALUE = "";

interface AssignSessionDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly courseId: string;
  readonly doc: DocumentResponse;
}

/**
 * T057 — assign-to-session control. A radio list of the course's sessions
 * (`useMeetings`) plus an "Unassigned" option; saving PATCHes the document's
 * `meeting_id` via `useAssignMaterial`. The foreign-meeting typed error
 * (`MEETING_NOT_FOUND`) surfaces as an in-dialog `StateBanner` (Decision 6);
 * any other failure shows a generic error, and the mutation invalidates the
 * materials + calendar queries on success.
 */
export function AssignSessionDialog({
  open,
  onOpenChange,
  courseId,
  doc,
}: AssignSessionDialogProps) {
  const t = useTranslations("teacher.materials.assign");
  const { data: meetings } = useMeetings(courseId);
  const assign = useAssignMaterial(courseId);

  const [choice, setChoice] = useState<string>(doc.meeting_id ?? UNASSIGNED_VALUE);
  const [error, setError] = useState<"notFound" | "generic" | null>(null);

  const sessions = useMemo(
    () => (meetings ? [...meetings].sort((a, b) => a.meeting_index - b.meeting_index) : []),
    [meetings]
  );

  const handleSave = async () => {
    setError(null);
    const next = choice === UNASSIGNED_VALUE ? null : choice;
    if (next === (doc.meeting_id ?? null)) {
      onOpenChange(false);
      return;
    }
    try {
      await assign.mutateAsync({ documentId: doc.id, meeting_id: next });
      onOpenChange(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "MEETING_NOT_FOUND") {
        setError("notFound");
      } else {
        setError("generic");
      }
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {t("subtitle", { name: doc.filename })}
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <StateBanner
            tone="warning"
            title={t("errorTitle")}
            reason={error === "notFound" ? t("notFound") : t("genericError")}
          />
        ) : null}

        <fieldset className="space-y-1.5">
          <legend className="mb-1 text-[12px] font-medium text-[var(--color-text-secondary)]">
            {t("sessionLabel")}
          </legend>
          <div className="max-h-64 space-y-1 overflow-y-auto">
            <SessionRadio
              label={t("unassign")}
              value={UNASSIGNED_VALUE}
              checked={choice === UNASSIGNED_VALUE}
              onSelect={setChoice}
            />
            {sessions.map((m) => (
              <SessionRadio
                key={m.id}
                label={
                  m.title
                    ? `${m.meeting_index}. ${m.title}`
                    : (m.topic_summary ?? String(m.meeting_index))
                }
                value={m.id}
                checked={choice === m.id}
                onSelect={setChoice}
              />
            ))}
          </div>
        </fieldset>

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
            disabled={assign.isPending}
            onClick={handleSave}
            data-icon="inline-start"
          >
            {assign.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Check aria-hidden="true" />
            )}
            {t("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface SessionRadioProps {
  readonly label: string;
  readonly value: string;
  readonly checked: boolean;
  readonly onSelect: (value: string) => void;
}

function SessionRadio({ label, value, checked, onSelect }: SessionRadioProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center gap-2.5 rounded-[var(--radius-md)] border px-3 py-2 text-[13px] transition-colors duration-[var(--duration-fast)]",
        checked
          ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-text)]"
          : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <input
        type="radio"
        name="assign-session"
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
        className="size-3.5 accent-[var(--color-primary)]"
      />
      <span className="truncate">{label}</span>
    </label>
  );
}
