"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowUpRight, Repeat2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Checkpoint } from "@/hooks/use-checkpoints";

interface CarryOverDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** The follow-up checkpoint currently open in the studio. */
  readonly checkpoint: Checkpoint;
  /** The resolved source checkpoint (`carried_from_id`), when it is loaded. */
  readonly source: Checkpoint | null;
  /** Deep-link into the source checkpoint's studio, when known. */
  readonly sourceHref?: string;
}

/**
 * T043 — carry-over suggestion modal. A `follow_up` checkpoint carries its weak
 * review points forward from a prior checkpoint (`carried_from_id`, §4.2). This
 * modal makes that lineage explicit: it explains why these cards are here and
 * links back to the source checkpoint so the teacher can compare before
 * publishing the revisit.
 */
export function CarryOverDialog({
  open,
  onOpenChange,
  checkpoint,
  source,
  sourceHref,
}: CarryOverDialogProps) {
  const t = useTranslations("teacher.studio.carryOver");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-accent)]/40 bg-[var(--color-accent-light)] px-4 py-3.5">
          <Repeat2
            aria-hidden="true"
            strokeWidth={1.85}
            className="mt-0.5 size-[18px] shrink-0 text-[var(--color-accent)]"
          />
          <div className="min-w-0 space-y-1">
            <p className="text-[13px] font-medium text-[var(--color-text)]">
              {checkpoint.title}
            </p>
            <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
              {source
                ? t("carriedFrom", { title: source.title })
                : t("carriedFromUnknown")}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("dismiss")}
          </Button>
          {source && sourceHref ? (
            <Button
              type="button"
              variant="default"
              render={<Link href={sourceHref} />}
            >
              {t("viewSource")}
              <ArrowUpRight aria-hidden="true" />
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
