"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import { useSubmitPhase } from "@/hooks/use-readiness";
import type { ReadinessPhaseDef } from "@/lib/pilot-config";

import {
  ReadinessQuestionField,
  emptyAnswer,
  type ReadinessAnswer,
} from "./readiness-question";

/** The readiness phases this step can render (each is a config question set). */
export type ReadinessPhaseName =
  | "eligibility_survey"
  | "ready_check"
  | "diagnostic";

interface StepReadinessPhaseProps {
  readonly phase: ReadinessPhaseName;
  readonly courseId: string;
  readonly code: string;
  /** Advance the funnel once the phase submits successfully. */
  readonly onDone: () => void;
  /** Optional back control (e.g. survey → preview). */
  readonly onBack?: () => void;
}

type AnswerMap = Readonly<Record<string, ReadinessAnswer>>;

/** Seed one answer slot per question, typed by kind, so inputs stay controlled. */
function seedAnswers(def: ReadinessPhaseDef): AnswerMap {
  return Object.fromEntries(
    def.questions.map((q) => [q.id, emptyAnswer(q.kind)])
  );
}

/**
 * S006 (eligibility survey) / S007 (ready check) — a single config-driven step
 * that renders whichever `ReadinessPhaseDef` matches `phase` from the pilot
 * config. Every question, label, and (for `scale`) the confidence scale come
 * from `usePilotConfig()` — nothing is hardcoded, so a different pilot config
 * renders a different survey. On "Continue" it POSTs the collected answers via
 * `useSubmitPhase` and calls `onDone()`. If the config has no def for the phase
 * (e.g. an optional phase a pilot omits), the step self-skips via `onDone()`.
 */
export function StepReadinessPhase({
  phase,
  courseId,
  code,
  onDone,
  onBack,
}: StepReadinessPhaseProps) {
  const t = useTranslations("student.join");
  const { config, isLoaded } = usePilotConfig();
  const submit = useSubmitPhase(courseId, code);

  const phaseDef = useMemo<ReadinessPhaseDef | null>(
    () => config?.readiness.find((p) => p.phase === phase) ?? null,
    [config, phase]
  );

  const [answers, setAnswers] = useState<AnswerMap>({});
  const [seededFor, setSeededFor] = useState<string | null>(null);

  // Reseed whenever the resolved phase definition changes (config arrives, or
  // the funnel reuses this component for the next phase). Adjusting state during
  // render is React's recommended alternative to a setState-in-effect reset —
  // it avoids the extra commit and the cascading-render lint warning.
  if (phaseDef && seededFor !== phaseDef.phase) {
    setSeededFor(phaseDef.phase);
    setAnswers(seedAnswers(phaseDef));
  }

  const setAnswer = useCallback((id: string, value: ReadinessAnswer) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
  }, []);

  // A pilot that omits this phase → skip it rather than dead-end the funnel.
  useEffect(() => {
    if (isLoaded && config && !phaseDef) onDone();
  }, [isLoaded, config, phaseDef, onDone]);

  const handleContinue = useCallback(async () => {
    try {
      await submit.mutateAsync({ phase, answers });
      onDone();
    } catch {
      // Error surfaced via the StateBanner below; funnel stays on this phase.
    }
  }, [answers, onDone, phase, submit]);

  if (!isLoaded) {
    return (
      <StateBanner
        tone="waiting"
        title={t("phase.loadingTitle")}
        reason={t("phase.loadingReason")}
      />
    );
  }

  if (!phaseDef) {
    // Config loaded but no def — the skip effect above will advance; render a
    // neutral waiting state for the brief interim.
    return <StateBanner tone="waiting" title={t("phase.loadingTitle")} />;
  }

  const confidenceScale = config!.confidence_scale;

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <h2 className="text-[18px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
          {phaseDef.title}
        </h2>
        <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          {phaseDef.intro}
        </p>
      </div>

      <div className="space-y-6 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        {phaseDef.questions.map((question) => (
          <ReadinessQuestionField
            key={question.id}
            question={question}
            confidenceScale={confidenceScale}
            value={answers[question.id] ?? emptyAnswer(question.kind)}
            onChange={(value) => setAnswer(question.id, value)}
            disabled={submit.isPending}
          />
        ))}
      </div>

      {submit.isError ? (
        <StateBanner
          tone="warning"
          title={t("phase.errorTitle")}
          reason={t("phase.errorReason")}
        />
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={onBack}
            disabled={submit.isPending}
          >
            {t("phase.back")}
          </Button>
        ) : (
          <span />
        )}
        <Button
          type="button"
          size="lg"
          onClick={handleContinue}
          disabled={submit.isPending}
        >
          {submit.isPending ? (
            <>
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              {t("phase.submitting")}
            </>
          ) : (
            t("phase.continue")
          )}
        </Button>
      </div>
    </div>
  );
}
