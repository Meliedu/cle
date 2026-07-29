"use client";

import { useTranslations } from "next-intl";
import { FileText } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { safeErrorFromCode, type SafeError } from "@/lib/contracts/safe-error";
import {
  sourceIsInFlight,
  sourceNeedsAttention,
  type SourceReadiness,
} from "@/lib/contracts/state";

/** One source row, already mapped onto the readiness axis by the caller. */
export interface SourceRow {
  readonly id: string;
  readonly name: string;
  readonly readiness: SourceReadiness;
  /** 0-100 while uploading or processing; null otherwise. */
  readonly progress: number | null;
  /** Typed failure code from the backend. Never a raw message. */
  readonly errorCode: string | null;
}

interface SourceStatusListProps {
  readonly sources: readonly SourceRow[];
  readonly onRetry: (source: SourceRow) => void;
  readonly onReplace: (source: SourceRow) => void;
  readonly isRetrying: boolean;
}

/**
 * The source list and its recovery affordance (Plate 05, rules 3 and 4).
 *
 *   Current   Raw exception text leaks implementation names and provides no
 *             trusted recovery.
 *   Target    Files are preserved; the failed source is named with Retry
 *             parsing and Replace file actions.
 *
 * The failure copy is built by `safeErrorFromCode` from a typed backend code.
 * There is no code path here that can render a backend message, so a future
 * regression on the server cannot leak an exception through this component.
 *
 * Status is announced through a polite live region, and the recovery banner is
 * not focus-stealing: focus stays where the user put it (safe failure rule 04).
 */
export function SourceStatusList({
  sources,
  onRetry,
  onReplace,
  isRetrying,
}: SourceStatusListProps) {
  const t = useTranslations("teacher.setup");

  const failed = sources.filter((source) => sourceNeedsAttention(source.readiness));

  return (
    <div className="space-y-5">
      <ul className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)]">
        {sources.map((source, index) => (
          <li
            key={source.id}
            className={cn(
              "bg-[var(--color-surface)]",
              index > 0 && "border-t border-[var(--color-border)]"
            )}
          >
            <div className="flex min-h-[60px] items-center gap-3 px-4 py-3">
              <span
                aria-hidden="true"
                className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-cream)]"
              >
                <FileText
                  className="size-4 text-[var(--color-primary-hover)]"
                  strokeWidth={1.85}
                  aria-hidden="true"
                />
              </span>

              <p className="min-w-0 flex-1 truncate text-[14px] font-medium text-[var(--color-text)]">
                {source.name}
                {source.progress !== null && sourceIsInFlight(source.readiness) ? (
                  <span className="ml-1.5 font-normal tabular-nums text-[var(--color-text-muted)]">
                    · {source.progress}%
                  </span>
                ) : null}
              </p>

              <ReadinessLabel readiness={source.readiness} />
            </div>

            {/* Progress bar sits under its own row, so it can never be read as
                belonging to the source below it. */}
            {sourceIsInFlight(source.readiness) ? (
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={source.progress ?? undefined}
                aria-label={source.name}
                className="h-[3px] w-full bg-[var(--color-border)]"
              >
                <div
                  className="h-full bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)] motion-reduce:transition-none"
                  style={{ width: `${source.progress ?? 10}%` }}
                />
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {/*
        Status changes are announced without moving focus (release acceptance,
        "Status"). `aria-live="polite"` waits for a pause rather than
        interrupting whatever the user is doing.
      */}
      <div aria-live="polite" className="space-y-4">
        {failed.map((source) => (
          <RecoveryBanner
            key={source.id}
            source={source}
            error={safeErrorFromCode(source.errorCode, { objectName: source.name })}
            onRetry={() => onRetry(source)}
            onReplace={() => onReplace(source)}
            isRetrying={isRetrying}
            retryLabel={t("retryParsing")}
            replaceLabel={t("replaceFile")}
            savedLabel={t("filesSaved")}
          />
        ))}
      </div>
    </div>
  );
}

function ReadinessLabel({ readiness }: { readonly readiness: SourceReadiness }) {
  const t = useTranslations("teacher.setup");

  const config: Record<
    SourceReadiness,
    { readonly key: string; readonly className: string }
  > = {
    idle: { key: "queued", className: "text-[var(--color-text-muted)]" },
    uploading: { key: "queued", className: "text-[var(--color-text-secondary)]" },
    processing: {
      key: "processing",
      className: "text-[var(--color-primary-hover)]",
    },
    ready: { key: "grounded", className: "text-[var(--color-success)]" },
    recoverable_error: { key: "failed", className: "text-[var(--color-error)]" },
    blocking_error: { key: "failed", className: "text-[var(--color-error)]" },
  };

  const { key, className } = config[readiness];
  return (
    <span className={cn("shrink-0 text-[13px] font-medium", className)}>
      {t(key)}
    </span>
  );
}

interface RecoveryBannerProps {
  readonly source: SourceRow;
  readonly error: SafeError;
  readonly onRetry: () => void;
  readonly onReplace: () => void;
  readonly isRetrying: boolean;
  readonly retryLabel: string;
  readonly replaceLabel: string;
  readonly savedLabel: string;
}

/**
 * The recovery banner.
 *
 * Copy order matches the safe failure contract, clause by clause: what was
 * preserved (the heading, because that is the user's first worry), what broke
 * and its consequence, then the safe next action.
 *
 * Retry is offered only when the typed code says the failure is retryable.
 * Replacing the file is always available, because it is the recovery of last
 * resort and never makes things worse.
 */
function RecoveryBanner({
  error,
  onRetry,
  onReplace,
  isRetrying,
  retryLabel,
  replaceLabel,
  savedLabel,
}: RecoveryBannerProps) {
  return (
    <section className="rounded-[var(--radius-xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] px-5 py-4">
      <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
        {savedLabel}
      </h3>
      <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-primary-hover)]">
        {error.title}. {error.nextAction}
      </p>
      <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {error.consequence} {error.preserved}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button size="xl" variant="outline" onClick={onReplace}>
          {replaceLabel}
        </Button>
        {error.retryable ? (
          <Button size="xl" onClick={onRetry} disabled={isRetrying}>
            {retryLabel}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
