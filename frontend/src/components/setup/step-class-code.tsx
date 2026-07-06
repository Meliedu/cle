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

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useSetStep } from "@/hooks/use-setup";
import {
  useCourse,
  useDeactivateEnrollCode,
  useRotateEnrollCode,
} from "@/hooks/use-courses";

interface StepClassCodeProps {
  readonly courseId: string;
  /** Fired after the `class_code` checklist flag is set. */
  readonly onComplete?: () => void;
}

/** A masked stand-in the same length as the code, shown until the teacher reveals it. */
function maskCode(code: string): string {
  return "•".repeat(Math.max(code.length, 8));
}

/**
 * T025 — class-code step. Surfaces the course `enroll_code`, kept hidden by
 * default (security-aware: the code is a shared secret students use to join) and
 * revealed only on request. The teacher can copy it, rotate to a fresh code
 * (`useRotateEnrollCode`, which invalidates the previous code and reactivates
 * joining), or deactivate joining without discarding the code
 * (`useDeactivateEnrollCode`). "Continue" flips the `class_code` checklist flag.
 * The P2 join-approval flow reads `enroll_code_active`; here we only manage it.
 */
export function StepClassCode({ courseId, onComplete }: StepClassCodeProps) {
  const t = useTranslations("teacher.setup.classCode");
  const { data: course, isLoading } = useCourse(courseId);
  const rotate = useRotateEnrollCode(courseId);
  const deactivate = useDeactivateEnrollCode(courseId);
  const setStep = useSetStep(courseId);

  const [revealed, setRevealed] = useState(false);
  const [copied, setCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const code = course?.enroll_code ?? "";
  const active = course?.enroll_code_active ?? false;

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

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "class_code", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const isBusy = rotate.isPending || deactivate.isPending;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        {isLoading ? (
          <EmptyState variant="waiting" title={t("loading")} />
        ) : !course ? (
          <StateBanner
            tone="warning"
            title={t("loadErrorTitle")}
            reason={t("loadError")}
          />
        ) : (
          <div className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-[13px] font-semibold text-[var(--color-text)]">
                {revealed ? t("codeVisibleLabel") : t("codeHiddenLabel")}
              </p>
              {active ? (
                <Badge variant="secondary">{t("active")}</Badge>
              ) : (
                <Badge variant="outline">{t("inactive")}</Badge>
              )}
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
                {revealed ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
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
          </div>
        )}

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={setStep.isPending || !course}
            onClick={() => void flipDone()}
          >
            {setStep.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : null}
            {t("continue")}
          </Button>
        </div>
      </div>

      <JoinAccessAside t={t} />
    </div>
  );
}

function JoinAccessAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const points = ["created", "share", "deactivate"] as const;
  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <ul className="mt-4 space-y-3">
        {points.map((point) => (
          <li key={point} className="flex gap-2.5">
            <KeyRound
              aria-hidden="true"
              strokeWidth={1.85}
              className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
            />
            <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
              {t(`aside.${point}`)}
            </p>
          </li>
        ))}
      </ul>
    </aside>
  );
}
