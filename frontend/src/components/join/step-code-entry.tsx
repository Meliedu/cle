"use client";

import { useCallback, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Join codes are 8 alphanumeric characters; strip everything else + uppercase. */
export function normalizeCode(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export const JOIN_CODE_LENGTH = 8;

interface StepCodeEntryProps {
  /** Called with a validated 8-char code; the funnel runs the lookup + branch. */
  readonly onSubmit: (code: string) => void;
  /** True while the lookup is in flight (disables the form). */
  readonly isSubmitting: boolean;
  /**
   * A server/network error message from the lookup (e.g. a failed request that
   * is neither "not found" nor "inactive" — those advance to S004). Length
   * validation is handled locally and takes precedence.
   */
  readonly submitError?: string | null;
}

/**
 * S003 — join-course-code entry. The first step of the student join funnel: an
 * 8-character code field that, on submit, hands a normalized code to the funnel
 * which resolves it (advance to preview) or branches to S004
 * (invalid/inactive). Length validation is local; server branches are the
 * funnel's job.
 */
export function StepCodeEntry({
  onSubmit,
  isSubmitting,
  submitError,
}: StepCodeEntryProps) {
  const t = useTranslations("student.join");
  const [code, setCode] = useState("");
  const [lengthError, setLengthError] = useState(false);

  const handleSubmit = useCallback(
    (event: { preventDefault: () => void }) => {
      event.preventDefault();
      const normalized = normalizeCode(code);
      if (normalized.length !== JOIN_CODE_LENGTH) {
        setLengthError(true);
        return;
      }
      setLengthError(false);
      onSubmit(normalized);
    },
    [code, onSubmit]
  );

  const error = lengthError
    ? t("code.lengthError")
    : submitError ?? null;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <Label htmlFor="join-code">{t("code.label")}</Label>
          <Input
            id="join-code"
            autoFocus
            autoComplete="off"
            spellCheck={false}
            inputMode="text"
            placeholder={t("code.placeholder")}
            value={code}
            onChange={(e) => {
              setCode(normalizeCode(e.target.value));
              if (lengthError) setLengthError(false);
            }}
            maxLength={12}
            disabled={isSubmitting}
            className="font-mono text-base uppercase tracking-[0.3em]"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "join-code-error" : "join-code-hint"}
          />
          {error ? (
            <p
              id="join-code-error"
              role="alert"
              className="text-[13px] text-[var(--color-error)]"
            >
              {error}
            </p>
          ) : (
            <p
              id="join-code-hint"
              className="text-[13px] text-[var(--color-text-muted)]"
            >
              {t("code.hint")}
            </p>
          )}
        </div>

        <Button
          type="submit"
          size="lg"
          disabled={isSubmitting}
          className="w-full"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {t("code.submitting")}
            </>
          ) : (
            t("code.submit")
          )}
        </Button>
      </div>
    </form>
  );
}
