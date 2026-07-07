"use client";

import { useMemo } from "react";
import { ClipboardCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import { EmptyState, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import type { ReadinessPhaseDef } from "@/lib/pilot-config";

import { StepReadinessPhase } from "./step-readiness-phase";

interface StepDiagnosticProps {
  readonly courseId: string;
  readonly code: string;
  /** Advance the funnel to the recommendation (S009). */
  readonly onDone: () => void;
  /** Return to the ready check (S007). */
  readonly onBack?: () => void;
}

/**
 * S008 — optional diagnostic task. Per Decision 4, the CLE pilot ships NO
 * `diagnostic` question set, so this step is optional and never blocks the
 * funnel. If a future pilot config adds a `diagnostic` `ReadinessPhaseDef`, we
 * render it through the same config-driven `StepReadinessPhase` used by the
 * survey / ready-check (Task 10) — nothing is hardcoded. When absent, we show a
 * brief "no diagnostic for this course" skip card with an explicit Continue so
 * the student always advances by choice rather than dead-ending on a blank step.
 */
export function StepDiagnostic({
  courseId,
  code,
  onDone,
  onBack,
}: StepDiagnosticProps) {
  const t = useTranslations("student.join");
  const { config, isLoaded } = usePilotConfig();

  const diagnosticDef = useMemo<ReadinessPhaseDef | null>(
    () => config?.readiness.find((p) => p.phase === "diagnostic") ?? null,
    [config]
  );

  if (!isLoaded) {
    return (
      <StateBanner
        tone="waiting"
        title={t("phase.loadingTitle")}
        reason={t("phase.loadingReason")}
      />
    );
  }

  // A pilot with a diagnostic question set renders it config-driven, exactly
  // like the survey / ready check.
  if (diagnosticDef) {
    return (
      <StepReadinessPhase
        phase="diagnostic"
        courseId={courseId}
        code={code}
        onDone={onDone}
        onBack={onBack}
      />
    );
  }

  // No diagnostic for this course — a skippable, non-blocking card.
  return (
    <div className="space-y-6">
      <EmptyState
        icon={ClipboardCheck}
        title={t("diagnostic.skipTitle")}
        reason={t("diagnostic.skipReason")}
      />

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button type="button" variant="outline" size="lg" onClick={onBack}>
            {t("diagnostic.back")}
          </Button>
        ) : (
          <span />
        )}
        <Button type="button" size="lg" onClick={onDone}>
          {t("diagnostic.continue")}
        </Button>
      </div>
    </div>
  );
}
