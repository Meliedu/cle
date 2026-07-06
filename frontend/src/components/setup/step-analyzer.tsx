"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  BookOpen,
  CalendarClock,
  Loader2,
  Sparkles,
  Target,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, StateBanner } from "@/components/patterns";
import {
  useAnalyzeSetup,
  useSetStep,
  useSetupAnalysis,
  type MissingSource,
  type SetupStepKey,
} from "@/hooks/use-setup";

interface StepAnalyzerProps {
  readonly courseId: string;
  /** Fired after the `analyzer_review` checklist flag is set. */
  readonly onComplete?: () => void;
  /** Jump back to an earlier wizard step to fix a missing source. */
  readonly onNavigate?: (step: SetupStepKey) => void;
}

/** Which earlier step fixes each missing-source kind (fallback: materials). */
const MISSING_SOURCE_STEP: Record<string, SetupStepKey> = {
  objective_without_source: "materials",
  session_without_material: "materials",
};

interface CountCard {
  readonly key: "documents" | "meetings" | "objectives";
  readonly icon: LucideIcon;
}

const COUNT_CARDS: readonly CountCard[] = [
  { key: "documents", icon: BookOpen },
  { key: "meetings", icon: CalendarClock },
  { key: "objectives", icon: Target },
];

/**
 * T019 — course-material-analyzer-review step. Triggers the `analyze_course_setup`
 * job (`useAnalyzeSetup`) and polls its result (`useSetupAnalysis`). Renders the
 * course map (document / session / outcome counts) and, when the analyzer flags
 * ungrounded outcomes or sessions, a warning banner listing each `missing_source`
 * with a link back to the step that fixes it. This is the real missing-source
 * gate (Task 13 decision): the teacher can still continue with warnings — the
 * hard block is at publish — so "Continue" flips `analyzer_review` regardless.
 */
export function StepAnalyzer({ courseId, onComplete, onNavigate }: StepAnalyzerProps) {
  const t = useTranslations("teacher.setup.analyzer");
  const analyze = useAnalyzeSetup(courseId);
  const setStep = useSetStep(courseId);
  const [started, setStarted] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: analysis, isLoading } = useSetupAnalysis(courseId, {
    poll: started,
  });

  // If a prior analysis already exists, land straight on the review rather than
  // an empty "Run" prompt — no need to have clicked Run this session.
  const hasResult = Boolean(analysis?.ready && analysis.analysis);

  const runAnalysis = useCallback(async () => {
    setActionError(null);
    setStarted(true);
    try {
      await analyze.mutateAsync();
    } catch {
      setActionError(t("runError"));
    }
  }, [analyze, t]);

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "analyzer_review", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const result = hasResult ? analysis?.analysis ?? null : null;
  const isRunning = started && !hasResult;
  const isFlipping = setStep.isPending;

  const missing = useMemo(
    () => result?.missing_sources ?? [],
    [result]
  );

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {!started && !hasResult ? (
        <div className="flex flex-col items-start gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="flex gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
              <Sparkles aria-hidden="true" strokeWidth={1.85} className="size-4.5" />
            </span>
            <div className="space-y-1">
              <p className="text-[14px] font-semibold text-[var(--color-text)]">
                {t("run.title")}
              </p>
              <p className="max-w-[52ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                {t("run.reason")}
              </p>
            </div>
          </div>
          <Button
            type="button"
            size="lg"
            disabled={analyze.isPending}
            onClick={() => void runAnalysis()}
          >
            {analyze.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {t("run.action")}
          </Button>
        </div>
      ) : isRunning || isLoading ? (
        <EmptyState variant="waiting" title={t("running.title")} reason={t("running.reason")} />
      ) : result ? (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-3">
            {COUNT_CARDS.map(({ key, icon: Icon }) => (
              <div
                key={key}
                className="space-y-2 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
              >
                <span className="flex size-8 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
                  <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
                </span>
                <p className="text-[24px] font-semibold leading-none tracking-tight text-[var(--color-text)]">
                  {result.counts[key]}
                </p>
                <p className="text-[12px] text-[var(--color-text-secondary)]">
                  {t(`counts.${key}`)}
                </p>
              </div>
            ))}
          </div>

          {result.has_missing_sources ? (
            <StateBanner
              tone="warning"
              title={t("missing.title", { count: missing.length })}
              reason={t("missing.reason")}
            />
          ) : (
            <StateBanner tone="success" title={t("ready.title")} reason={t("ready.reason")} />
          )}

          {result.has_missing_sources ? (
            <ul aria-label={t("missing.listLabel")} className="space-y-2.5">
              {missing.map((source) => (
                <MissingSourceRow
                  key={`${source.kind}-${source.id}`}
                  source={source}
                  onNavigate={onNavigate}
                  t={t}
                />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {actionError ? (
        <p role="alert" className="text-[13px] text-[var(--color-error)]">
          {actionError}
        </p>
      ) : null}

      {result ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
            {t("continue")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={analyze.isPending}
            onClick={() => void runAnalysis()}
          >
            {t("rerun")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

interface MissingSourceRowProps {
  readonly source: MissingSource;
  readonly onNavigate?: (step: SetupStepKey) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function MissingSourceRow({ source, onNavigate, t }: MissingSourceRowProps) {
  const targetStep = MISSING_SOURCE_STEP[source.kind] ?? "materials";
  return (
    <li className="flex items-start justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-warning)]/40 bg-[var(--color-warning-light)] p-3.5">
      <div className="min-w-0 space-y-0.5">
        <p className="text-[12px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
          {t(`missing.kind.${source.kind}`)}
        </p>
        <p className="truncate text-[13px] text-[var(--color-text)]">{source.label}</p>
      </div>
      {onNavigate ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="shrink-0"
          onClick={() => onNavigate(targetStep)}
        >
          {t("missing.fix")}
        </Button>
      ) : null}
    </li>
  );
}
