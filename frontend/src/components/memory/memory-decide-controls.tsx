"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StateBanner } from "@/components/patterns";
import {
  useDecideMemory,
  type MemoryDecision,
  type MemoryItemResponse,
} from "@/hooks/use-memory";

import { DECISION_CHOICES, DECISION_ICON } from "./memory-format";

interface MemoryDecideControlsProps {
  readonly courseId: string;
  readonly item: MemoryItemResponse;
}

/**
 * The T087 decide controls — four decision buttons (`carry_forward | keep |
 * revise | reject`), each gated behind a confirm dialog that spells out the
 * decision is written to the course audit log. Reject is styled destructive.
 * Wraps `useDecideMemory`; a failed write surfaces an inline `StateBanner`.
 */
export function MemoryDecideControls({
  courseId,
  item,
}: MemoryDecideControlsProps) {
  const t = useTranslations("teacher.memory.decide");
  const tDecision = useTranslations("teacher.memory.decision");
  const decide = useDecideMemory(courseId);
  const [pending, setPending] = useState<MemoryDecision | null>(null);

  function confirm(decision: MemoryDecision) {
    decide.mutate(
      { itemId: item.id, decision },
      { onSuccess: () => setPending(null) }
    );
  }

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="space-y-1">
        <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
          {t("heading")}
        </h3>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("prompt")}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2.5">
        {DECISION_CHOICES.map((decision) => {
          const Icon = DECISION_ICON[decision];
          const active = item.decision === decision;
          const isReject = decision === "reject";
          return (
            <Button
              key={decision}
              type="button"
              variant={active ? "default" : isReject ? "destructive" : "outline"}
              className={cn(
                "h-auto justify-start gap-2 px-3 py-2.5",
                active && "ring-1 ring-[var(--color-primary)]/40"
              )}
              disabled={decide.isPending}
              onClick={() => setPending(decision)}
            >
              <Icon aria-hidden="true" className="size-4" />
              <span className="text-[13px] font-medium">
                {tDecision(decision)}
              </span>
            </Button>
          );
        })}
      </div>

      <p className="flex items-start gap-2 text-[12px] leading-relaxed text-[var(--color-text-muted)]">
        <ShieldCheck
          aria-hidden="true"
          strokeWidth={1.85}
          className="mt-0.5 size-3.5 shrink-0 text-[var(--color-text-muted)]"
        />
        {t("audited")}
      </p>

      {decide.isError ? (
        <StateBanner tone="warning" title={t("error")} />
      ) : null}

      <Dialog
        open={pending !== null}
        onOpenChange={(open) => {
          if (!open) setPending(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("confirmTitle")}</DialogTitle>
            <DialogDescription>
              {pending
                ? t("confirmBody", { decision: tDecision(pending) })
                : null}
            </DialogDescription>
          </DialogHeader>
          <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
            {t("audited")}
          </p>
          <DialogFooter>
            <DialogClose
              render={<Button variant="outline" disabled={decide.isPending} />}
            >
              {t("cancel")}
            </DialogClose>
            <Button
              type="button"
              variant={pending === "reject" ? "destructive" : "default"}
              disabled={decide.isPending}
              onClick={() => pending && confirm(pending)}
            >
              {decide.isPending ? t("saving") : t("confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
