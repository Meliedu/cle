"use client";

import { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StateBanner } from "@/components/patterns";
import { ApiError } from "@/lib/api";

interface ReportConfirmDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: string;
  readonly body: string;
  readonly confirmLabel: string;
  readonly cancelLabel: string;
  readonly pendingLabel: string;
  readonly genericErrorLabel: string;
  /** Perform the transition; rejects with an `ApiError` on a gate/transition 409. */
  readonly onConfirm: () => Promise<void>;
  readonly isPending: boolean;
  /**
   * Map a typed `ApiError.code` to a designed blocked-banner reason. Return
   * `null` to fall through to the generic error line.
   */
  readonly blockedReasonFor: (code: string | undefined) => string | null;
}

/**
 * Confirmation dialog for the approve / send transitions (T083). Mirrors the
 * `PublishGateDialog` shape: a confirm CTA that runs the mutation, surfaces a
 * typed 409 (`REPORT_INVALID_TRANSITION` / `REPORT_NOT_REVIEWED`) as a
 * `StateBanner tone="blocked"`, and any other failure as an inline error.
 */
export function ReportConfirmDialog({
  open,
  onOpenChange,
  title,
  body,
  confirmLabel,
  cancelLabel,
  pendingLabel,
  genericErrorLabel,
  onConfirm,
  isPending,
  blockedReasonFor,
}: ReportConfirmDialogProps) {
  const [blockedReason, setBlockedReason] = useState<string | null>(null);
  const [genericError, setGenericError] = useState(false);

  const confirm = useCallback(async () => {
    setBlockedReason(null);
    setGenericError(false);
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (error) {
      const code = error instanceof ApiError ? error.code : undefined;
      const reason = blockedReasonFor(code);
      if (reason) {
        setBlockedReason(reason);
      } else {
        setGenericError(true);
      }
    }
  }, [onConfirm, onOpenChange, blockedReasonFor]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{body}</DialogDescription>
        </DialogHeader>

        {blockedReason ? (
          <StateBanner tone="blocked" title={title} reason={blockedReason} />
        ) : null}
        {genericError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {genericErrorLabel}
          </p>
        ) : null}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            disabled={isPending}
            onClick={() => void confirm()}
          >
            {isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : null}
            {isPending ? pendingLabel : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
