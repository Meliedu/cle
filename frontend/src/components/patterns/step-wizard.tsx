import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Per-step visual state on the rail. One treatment per status. */
export type WizardStepStatus = "upcoming" | "current" | "complete" | "blocked";

export interface WizardStep {
  /** Stable id; matched against `currentId` and passed to `onStepSelect`. */
  readonly id: string;
  /** Human label shown on the rail (already localized by the caller). */
  readonly label: string;
  /** The step's requirements are satisfied. */
  readonly complete: boolean;
  /** The step is gated (a prerequisite failed); rendered non-navigable. */
  readonly blocked?: boolean;
  /** Optional one-line hint under the label. */
  readonly description?: string;
}

export interface StepWizardProps
  extends Omit<React.ComponentProps<"div">, "onSelect"> {
  /** Ordered steps rendered on the rail. */
  readonly steps: readonly WizardStep[];
  /** Id of the step whose content is currently shown. */
  readonly currentId: string;
  /** Active step content. */
  readonly children: ReactNode;
  /**
   * Called when the teacher clicks a navigable rail step. Only `complete` or
   * `current` steps are interactive — the wizard never lets you jump ahead.
   */
  readonly onStepSelect?: (id: string) => void;
  /** Called by the Back control. Disabled on the first step. */
  readonly onBack?: () => void;
  /** Called by the Next control. Disabled on the last step. */
  readonly onNext?: () => void;
  /** Called by the Save control. The control is hidden when omitted. */
  readonly onSave?: () => void;
  /** Disables the Save control while a save is in flight. */
  readonly isSaving?: boolean;
  readonly backLabel?: string;
  readonly nextLabel?: string;
  readonly saveLabel?: string;
  /** Progress caption; defaults to `Step {n} of {total}`. */
  readonly progressLabel?: string;
}

/** Pure status derivation — the current step always wins so it stays highlighted. */
export function stepStatus(
  step: WizardStep,
  currentId: string
): WizardStepStatus {
  if (step.id === currentId) return "current";
  if (step.complete) return "complete";
  if (step.blocked) return "blocked";
  return "upcoming";
}

const STATUS_MARKER: Record<WizardStepStatus, string> = {
  complete:
    "border-transparent bg-[var(--color-success)] text-[var(--color-on-accent)]",
  current:
    "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]",
  blocked:
    "border-[var(--color-error)]/45 bg-[var(--color-error-light)] text-[var(--color-error)]",
  upcoming:
    "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]",
};

const STATUS_LABEL_COLOR: Record<WizardStepStatus, string> = {
  complete: "text-[var(--color-text)]",
  current: "text-[var(--color-text)] font-semibold",
  blocked: "text-[var(--color-error)]",
  upcoming: "text-[var(--color-text-muted)]",
};

/**
 * Reusable multi-step wizard shell: a status rail on the left, the active
 * step's content on the right, and a footer with Back / Save / Next controls
 * plus a progress caption. It is deliberately domain-agnostic — it takes a
 * `steps` array and renders whatever child the caller places in the content
 * slot. Tokens only; matches the `patterns/` visual idiom.
 */
export function StepWizard({
  steps,
  currentId,
  children,
  onStepSelect,
  onBack,
  onNext,
  onSave,
  isSaving = false,
  backLabel = "Back",
  nextLabel = "Next",
  saveLabel = "Save",
  progressLabel,
  className,
  ...rest
}: StepWizardProps) {
  const total = steps.length;
  const currentIndex = steps.findIndex((s) => s.id === currentId);
  const isFirst = currentIndex <= 0;
  const isLast = currentIndex === -1 || currentIndex === total - 1;
  const progress = progressLabel ?? `Step ${currentIndex + 1} of ${total}`;
  const pct = total > 0 ? ((currentIndex + 1) / total) * 100 : 0;

  return (
    <div
      data-current-step={currentId}
      className={cn(
        "flex flex-col gap-8 md:flex-row md:gap-10",
        className
      )}
      {...rest}
    >
      <nav aria-label="Setup steps" className="md:w-64 md:shrink-0">
        <ol className="flex flex-col gap-1">
          {steps.map((step, index) => {
            const status = stepStatus(step, currentId);
            const navigable =
              Boolean(onStepSelect) &&
              (status === "complete" || status === "current");
            const marker =
              status === "complete" ? (
                <Check aria-hidden="true" className="size-3.5" strokeWidth={2.5} />
              ) : (
                index + 1
              );

            const inner = (
              <>
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-7 shrink-0 items-center justify-center rounded-full border text-[13px] font-semibold",
                    STATUS_MARKER[status]
                  )}
                >
                  {marker}
                </span>
                <span className="min-w-0 flex-1 space-y-0.5">
                  <span
                    className={cn(
                      "block truncate text-[14px] leading-snug tracking-tight",
                      STATUS_LABEL_COLOR[status]
                    )}
                  >
                    {step.label}
                  </span>
                  {step.description ? (
                    <span className="block truncate text-[12px] leading-snug text-[var(--color-text-muted)]">
                      {step.description}
                    </span>
                  ) : null}
                </span>
              </>
            );

            return (
              <li
                key={step.id}
                aria-label={step.label}
                aria-current={status === "current" ? "step" : undefined}
                data-status={status}
                className="list-none"
              >
                {navigable ? (
                  <button
                    type="button"
                    onClick={() => onStepSelect?.(step.id)}
                    className="flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-2.5 py-2 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
                  >
                    {inner}
                  </button>
                ) : (
                  <div className="flex w-full items-center gap-3 rounded-[var(--radius-lg)] px-2.5 py-2">
                    {inner}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      <div className="flex min-w-0 flex-1 flex-col gap-6">
        <section
          aria-live="polite"
          className="min-w-0 flex-1"
        >
          {children}
        </section>

        <footer className="flex flex-col gap-4 border-t border-[var(--color-border)]/70 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack}
              disabled={isFirst || !onBack}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] px-3.5 py-2 text-[14px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              <ChevronLeft aria-hidden="true" className="size-4" strokeWidth={2} />
              {backLabel}
            </button>
            {onSave ? (
              <button
                type="button"
                onClick={onSave}
                disabled={isSaving}
                className="rounded-[var(--radius-md)] px-3.5 py-2 text-[14px] font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-45"
              >
                {saveLabel}
              </button>
            ) : null}
          </div>

          <div className="flex items-center gap-3">
            <span className="text-[13px] font-medium text-[var(--color-text-muted)]">
              {progress}
            </span>
            <div
              role="progressbar"
              aria-valuenow={currentIndex + 1}
              aria-valuemin={1}
              aria-valuemax={Math.max(total, 1)}
              className="h-1.5 w-24 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
            >
              <div
                className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)] transition-[width]"
                style={{ width: `${pct}%` }}
              />
            </div>
            <button
              type="button"
              onClick={onNext}
              disabled={isLast || !onNext}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-primary)] px-4 py-2 text-[14px] font-semibold text-[var(--color-text-on-primary)] transition-colors hover:bg-[var(--color-primary-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-45"
            >
              {nextLabel}
              <ChevronRight aria-hidden="true" className="size-4" strokeWidth={2} />
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
