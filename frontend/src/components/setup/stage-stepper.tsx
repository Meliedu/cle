"use client";

import { useTranslations } from "next-intl";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  SETUP_STAGES,
  type SetupStage,
  type StageStatus,
} from "@/lib/setup-stages";

interface StageStepperProps {
  readonly statuses: Record<SetupStage, StageStatus>;
  readonly reachable: Record<SetupStage, boolean>;
  readonly progress: Record<SetupStage, { done: number; total: number }>;
  readonly onSelect: (stage: SetupStage) => void;
}

/**
 * The five-stage progress rail (Plate 05, rule 1).
 *
 * Ten implementation steps became five stages. The sub-steps did not disappear:
 * each stage shows its own "2 of 3 done" count, so the underlying granularity
 * is still legible without promoting every backend operation to a top-level
 * step.
 *
 * A stage the user cannot open yet is rendered as a disabled button with an
 * explanation, not hidden. Hiding it would make the flow's length unknowable.
 */
export function StageStepper({
  statuses,
  reachable,
  progress,
  onSelect,
}: StageStepperProps) {
  const t = useTranslations("teacher.setup");

  return (
    <nav aria-label={t("stepperLabel")}>
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-3">
        {SETUP_STAGES.map((stage, index) => {
          const status = statuses[stage];
          const canOpen = reachable[stage];
          const { done, total } = progress[stage];
          const label = t(`stages.${stage}`);

          return (
            <li key={stage} className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => canOpen && onSelect(stage)}
                disabled={!canOpen}
                aria-current={status === "current" ? "step" : undefined}
                aria-label={
                  canOpen
                    ? total > 0
                      ? `${label}, ${t("stageProgress", { done, total })}`
                      : label
                    : t("stageLocked", { stage: label })
                }
                className={cn(
                  "flex h-11 items-center gap-2.5 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium outline-none transition-colors duration-[var(--duration-fast)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
                  canOpen
                    ? "hover:bg-[var(--color-surface-hover)]"
                    : "cursor-not-allowed opacity-55",
                  status === "current"
                    ? "text-[var(--color-text)]"
                    : "text-[var(--color-text-secondary)]"
                )}
              >
                {/*
                  The marker distinguishes the three states by SHAPE as well as
                  color: a filled tick for complete, a ring for current, a plain
                  outline for pending.
                */}
                <span
                  aria-hidden="true"
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold tabular-nums",
                    status === "complete"
                      ? "border-[var(--color-success)] bg-[var(--color-success)] text-white"
                      : status === "current"
                        ? "border-[3px] border-[var(--color-primary)] bg-[var(--color-surface)] text-[var(--color-primary-hover)]"
                        : "border-[var(--color-border-hover)] bg-[var(--color-surface)] text-[var(--color-text-muted)]"
                  )}
                >
                  {status === "complete" ? (
                    <Check
                      className="size-3.5"
                      strokeWidth={3}
                      aria-hidden="true"
                    />
                  ) : (
                    index + 1
                  )}
                </span>

                <span className="flex flex-col items-start leading-tight">
                  <span
                    className={cn(
                      status === "current" && "font-semibold"
                    )}
                  >
                    {label}
                  </span>
                  {total > 0 && status !== "complete" ? (
                    <span className="text-[11px] text-[var(--color-text-muted)]">
                      {t("stageProgress", { done, total })}
                    </span>
                  ) : null}
                </span>
              </button>

              {index < SETUP_STAGES.length - 1 ? (
                <span
                  aria-hidden="true"
                  className="hidden h-px w-6 bg-[var(--color-border)] sm:block"
                />
              ) : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
