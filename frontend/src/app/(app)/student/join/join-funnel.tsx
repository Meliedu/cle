"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { StepCodeEntry } from "@/components/join/step-code-entry";
import { StepShortPreview } from "@/components/join/step-short-preview";
import { StepReadinessPhase } from "@/components/join/step-readiness-phase";
import { StepDiagnostic } from "@/components/join/step-diagnostic";
import { StepRecommendation } from "@/components/join/step-recommendation";
import { StepDeepPreview } from "@/components/join/step-deep-preview";
import { StepReadinessSummary } from "@/components/join/step-readiness-summary";
import {
  StateInvalidCode,
  type InvalidCodeReason,
} from "@/components/join/state-invalid-code";
import {
  branchFromLookup,
  joinErrorReason,
  useLookupCode,
  type CourseLookup,
} from "@/hooks/use-enrollment";

/**
 * The full join funnel steps (S003 → … → terminal). Tasks 9–10 wire `code`
 * (S003), `invalid_code` (S004), `preview` (S005 short preview), `survey`
 * (S006 eligibility survey) and `ready_check` (S007) — all config-driven from
 * the pilot readiness definitions. The later steps (diagnostic / recommendation
 * / deep_preview / summary / success / pending) are declared here so the
 * container's shape is stable as Tasks 11–12 fill them in.
 */
export type FunnelStep =
  | "code"
  | "invalid_code"
  | "preview"
  | "survey"
  | "ready_check"
  | "diagnostic"
  | "recommendation"
  | "deep_preview"
  | "summary"
  | "success"
  | "pending";

interface FunnelState {
  readonly step: FunnelStep;
  readonly code: string;
  readonly courseId: string | null;
  readonly lookup: CourseLookup | null;
  readonly invalidReason: InvalidCodeReason;
}

const INITIAL_STATE: FunnelState = {
  step: "code",
  code: "",
  courseId: null,
  lookup: null,
  invalidReason: "not_found",
};

/**
 * Client orchestrator for the student join funnel. Owns the funnel step state
 * and the code-lookup mutation; S003 hands it a normalized code, it resolves
 * the code and either advances (valid + active) or drops to S004
 * (invalid/inactive). A `pending` student never reaches the workspace here —
 * enrollment is the funnel's terminal step (Task 12), not this scaffold.
 */
export function JoinFunnel() {
  const t = useTranslations("student.join");
  const router = useRouter();
  const lookup = useLookupCode();

  const [state, setState] = useState<FunnelState>(INITIAL_STATE);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const goToInvalid = useCallback((reason: InvalidCodeReason) => {
    setState((prev) => ({ ...prev, step: "invalid_code", invalidReason: reason }));
  }, []);

  const goTo = useCallback((step: FunnelStep) => {
    setState((prev) => ({ ...prev, step }));
  }, []);

  const handleCodeSubmit = useCallback(
    async (code: string) => {
      setSubmitError(null);
      try {
        const result = await lookup.mutateAsync(code);
        const branch = branchFromLookup(result);
        if (branch.kind === "invalid") {
          goToInvalid(branch.reason);
          return;
        }
        setState({
          step: "preview",
          code,
          courseId: branch.courseId,
          lookup: branch.lookup,
          invalidReason: "not_found",
        });
      } catch (error: unknown) {
        const reason = joinErrorReason(error);
        // Unknown/mistyped code → S004; anything else stays on S003 with an
        // inline retry message (network/auth/server).
        if (reason === "invalid") {
          goToInvalid("not_found");
          return;
        }
        setSubmitError(t("code.lookupError"));
      }
    },
    [goToInvalid, lookup, t]
  );

  const resetToCode = useCallback(() => {
    setSubmitError(null);
    setState(INITIAL_STATE);
    lookup.reset();
  }, [lookup]);

  const backToCourses = useCallback(() => {
    router.push("/student/courses");
  }, [router]);

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {state.step === "code" ? (
        <StepCodeEntry
          onSubmit={handleCodeSubmit}
          isSubmitting={lookup.isPending}
          submitError={submitError}
        />
      ) : state.step === "invalid_code" ? (
        <StateInvalidCode
          reason={state.invalidReason}
          onTryAgain={resetToCode}
          onBackToCourses={backToCourses}
        />
      ) : state.step === "preview" && state.courseId ? (
        <StepShortPreview
          courseId={state.courseId}
          code={state.code}
          onStart={() => goTo("survey")}
          onBack={resetToCode}
        />
      ) : state.step === "survey" && state.courseId ? (
        <StepReadinessPhase
          phase="eligibility_survey"
          courseId={state.courseId}
          code={state.code}
          onDone={() => goTo("ready_check")}
          onBack={() => goTo("preview")}
        />
      ) : state.step === "ready_check" && state.courseId ? (
        <StepReadinessPhase
          phase="ready_check"
          courseId={state.courseId}
          code={state.code}
          onDone={() => goTo("diagnostic")}
          onBack={() => goTo("survey")}
        />
      ) : state.step === "diagnostic" && state.courseId ? (
        <StepDiagnostic
          courseId={state.courseId}
          code={state.code}
          onDone={() => goTo("recommendation")}
          onBack={() => goTo("ready_check")}
        />
      ) : state.step === "recommendation" && state.courseId ? (
        <StepRecommendation
          courseId={state.courseId}
          code={state.code}
          onContinue={() => goTo("deep_preview")}
          onBack={() => goTo("diagnostic")}
        />
      ) : state.step === "deep_preview" && state.courseId ? (
        <StepDeepPreview
          courseId={state.courseId}
          code={state.code}
          onContinue={() => goTo("summary")}
          onBack={() => goTo("recommendation")}
        />
      ) : state.step === "summary" && state.courseId ? (
        <StepReadinessSummary
          courseId={state.courseId}
          code={state.code}
          onJoin={() => goTo("success")}
          onBack={() => goTo("deep_preview")}
        />
      ) : (
        <div className="space-y-6">
          {/*
            Placeholder for the terminal join states (S012/S013) that Task 12
            fills in: course-not-open, pending-approval, and join-success. The
            readiness summary's "Join course" CTA advances here; until Task 12
            wires the enroll action the funnel parks on this state rather than
            dead-ending on a blank div.
          */}
          <StateBanner
            tone="info"
            title={t("comingSoon.title")}
            reason={t("comingSoon.reason")}
          />
          <Button type="button" variant="outline" size="lg" onClick={resetToCode}>
            {t("comingSoon.back")}
          </Button>
        </div>
      )}
    </div>
  );
}
