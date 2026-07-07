"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { StepCodeEntry } from "@/components/join/step-code-entry";
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
 * The full join funnel steps (S003 → … → terminal). This scaffold implements
 * only `code` (S003) and `invalid_code` (S004), advancing a valid code to a
 * `preview` placeholder that Task 10 replaces with S005. The later readiness
 * steps (survey / ready_check / diagnostic / recommendation / deep_preview /
 * summary / success / pending) are declared here so the container's shape is
 * stable as Tasks 10–12 fill them in.
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
      ) : state.step === "preview" ? (
        <div className="space-y-6">
          {/*
            Placeholder for S005 short-course-preview (Task 10). The code
            resolved cleanly; the readiness funnel picks up from the captured
            `courseId` + `code`.
          */}
          <StateBanner
            tone="info"
            title={t("preview.comingSoonTitle")}
            reason={t("preview.comingSoonReason")}
          />
          <Button type="button" variant="outline" size="lg" onClick={resetToCode}>
            {t("preview.back")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
