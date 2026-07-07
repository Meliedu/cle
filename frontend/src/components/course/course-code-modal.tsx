"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  RefreshCw,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { StateBanner } from "@/components/patterns";
import {
  useCourse,
  useDeactivateEnrollCode,
  useRotateEnrollCode,
} from "@/hooks/use-courses";

interface CourseCodeModalProps {
  readonly courseId: string;
}

/** A masked stand-in the same length as the code, shown until the teacher reveals it. */
function maskCode(code: string): string {
  return "•".repeat(Math.max(code.length, 8));
}

/**
 * T034 — course-code modal. The teacher's quick-access join-code management
 * from the enrollment / overview page: reveal (masked by default), copy, rotate
 * to a fresh code, or deactivate joining — reusing the P1 class-code
 * affordances (`useRotateEnrollCode` / `useDeactivateEnrollCode`, same masking
 * treatment as `StepClassCode`) but as a modal rather than the full setup step.
 * The `join_mode` (instant code vs code + approval) is surfaced READ-ONLY here:
 * there is no PATCH endpoint for it in P2, so editing stays out of scope (flag
 * for a later phase). A trigger button owns its own open state.
 */
export function CourseCodeModal({ courseId }: CourseCodeModalProps) {
  const t = useTranslations("teacher.enrollment.codeModal");
  const { data: course, isLoading } = useCourse(courseId);
  const rotate = useRotateEnrollCode(courseId);
  const deactivate = useDeactivateEnrollCode(courseId);

  const [open, setOpen] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const code = course?.enroll_code ?? "";
  const active = course?.enroll_code_active ?? false;
  const requiresApproval = course?.join_mode === "code_plus_approval";

  const handleOpenChange = useCallback((next: boolean) => {
    setOpen(next);
    if (!next) {
      // Re-hide the shared secret whenever the modal closes.
      setRevealed(false);
      setCopied(false);
      setActionError(null);
    }
  }, []);

  const copyCode = useCallback(async () => {
    setActionError(null);
    try {
      await navigator.clipboard.writeText(code);
      setRevealed(true);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setActionError(t("copyError"));
    }
  }, [code, t]);

  const rotateCode = useCallback(async () => {
    setActionError(null);
    try {
      await rotate.mutateAsync();
      setRevealed(true);
    } catch {
      setActionError(t("rotateError"));
    }
  }, [rotate, t]);

  const deactivateCode = useCallback(async () => {
    setActionError(null);
    try {
      await deactivate.mutateAsync();
    } catch {
      setActionError(t("deactivateError"));
    }
  }, [deactivate, t]);

  const isBusy = rotate.isPending || deactivate.isPending;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
      >
        <KeyRound aria-hidden="true" />
        {t("trigger")}
      </Button>

      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        {isLoading || !course ? (
          <StateBanner tone="waiting" title={t("loading")} />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              {active ? (
                <Badge variant="secondary">{t("active")}</Badge>
              ) : (
                <Badge variant="outline">{t("inactive")}</Badge>
              )}
              <Badge variant="outline">
                {requiresApproval ? t("approvalMode") : t("codeMode")}
              </Badge>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <code
                aria-label={t("codeLabel")}
                className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-4 py-2.5 font-mono text-[18px] font-semibold tracking-[0.2em] text-[var(--color-text)]"
              >
                {revealed ? code : maskCode(code)}
              </code>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setRevealed((v) => !v)}
              >
                {revealed ? (
                  <EyeOff aria-hidden="true" />
                ) : (
                  <Eye aria-hidden="true" />
                )}
                {revealed ? t("hide") : t("reveal")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => void copyCode()}
              >
                {copied ? (
                  <Check aria-hidden="true" className="text-[var(--color-success)]" />
                ) : (
                  <Copy aria-hidden="true" />
                )}
                {copied ? t("copied") : t("copy")}
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 border-t border-[var(--color-border)] pt-4">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={isBusy}
                onClick={() => void rotateCode()}
              >
                {rotate.isPending ? (
                  <Loader2 aria-hidden="true" className="animate-spin" />
                ) : (
                  <RefreshCw aria-hidden="true" />
                )}
                {active ? t("rotate") : t("reactivate")}
              </Button>
              {active ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="text-[var(--color-error)]"
                  disabled={isBusy}
                  onClick={() => void deactivateCode()}
                >
                  {deactivate.isPending ? (
                    <Loader2 aria-hidden="true" className="animate-spin" />
                  ) : null}
                  {t("deactivate")}
                </Button>
              ) : null}
            </div>

            <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
              {active ? t("activeHint") : t("inactiveHint")}
            </p>

            {actionError ? (
              <p role="alert" className="text-[13px] text-[var(--color-error)]">
                {actionError}
              </p>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
