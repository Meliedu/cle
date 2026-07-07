"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageHeader } from "@/components/patterns";
import { StepCodeEntry } from "@/components/join/step-code-entry";
import { StepShortPreview } from "@/components/join/step-short-preview";
import { StepReadinessPhase } from "@/components/join/step-readiness-phase";
import { StepDiagnostic } from "@/components/join/step-diagnostic";
import { StepRecommendation } from "@/components/join/step-recommendation";
import { StepDeepPreview } from "@/components/join/step-deep-preview";
import { StepReadinessSummary } from "@/components/join/step-readiness-summary";
import { StateJoinSuccess } from "@/components/join/state-join-success";
import { StatePendingApproval } from "@/components/join/state-pending-approval";
import { StateCourseNotOpen } from "@/components/join/state-course-not-open";
import {
  StateInvalidCode,
  type InvalidCodeReason,
} from "@/components/join/state-invalid-code";
import {
  branchFromEnroll,
  branchFromLookup,
  joinErrorReason,
  useEnrollByCode,
  useLookupCode,
  type CourseLookup,
} from "@/hooks/use-enrollment";

/**
 * The full join funnel steps (S003 → … → terminal). Tasks 9–11 wire `code`
 * (S003) through `summary` (S011); Task 12 lands the terminal states: `success`
 * (S013), `pending` (awaiting approval), and `not_open` (S012). `invalid_code`
 * (S004) doubles as the terminal for a deactivated code discovered at join time.
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
  | "pending"
  | "not_open";

interface FunnelState {
  readonly step: FunnelStep;
  readonly code: string;
  readonly courseId: string | null;
  readonly lookup: CourseLookup | null;
  readonly invalidReason: InvalidCodeReason;
  /** The joined course's name, captured from the enroll result for S012/S013. */
  readonly courseName: string;
}

const INITIAL_STATE: FunnelState = {
  step: "code",
  code: "",
  courseId: null,
  lookup: null,
  invalidReason: "not_found",
  courseName: "",
};

interface JoinFunnelProps {
  /** Deep-link prefill from `/student/join?code=XXXX` (emailed invite link). */
  readonly initialCode?: string;
}

/**
 * Client orchestrator for the student join funnel. Owns the funnel step state,
 * the code-lookup mutation, and the terminal `enroll-by-code` action. S003 hands
 * it a normalized code; it resolves and either advances (valid + active) or
 * drops to S004. The summary's "Join course" CTA runs the real enroll and
 * branches to a terminal screen — a `pending` student is NEVER routed into the
 * workspace (a code_plus_approval course is unreadable until approved).
 */
export function JoinFunnel({ initialCode }: JoinFunnelProps) {
  const t = useTranslations("student.join");
  const router = useRouter();
  const lookup = useLookupCode();
  const enroll = useEnrollByCode();

  const [state, setState] = useState<FunnelState>(INITIAL_STATE);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);

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
          courseName: branch.lookup.name,
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

  /**
   * Terminal join. Runs `enroll-by-code` and branches identically to the dialog:
   * active → S013, pending → awaiting-approval. Gate errors map to their state:
   * SETUP_NOT_OPEN → S012, JOIN_CODE_INACTIVE → S004; anything else stays on the
   * summary with an inline retry message.
   */
  const handleJoin = useCallback(async () => {
    setJoinError(null);
    try {
      const result = await enroll.mutateAsync(state.code);
      const branch = branchFromEnroll(result);
      setState((prev) => ({
        ...prev,
        step: branch.kind === "pending" ? "pending" : "success",
        courseId: branch.course.id,
        courseName: branch.course.name,
      }));
    } catch (error: unknown) {
      const reason = joinErrorReason(error);
      if (reason === "not_open") {
        goTo("not_open");
        return;
      }
      if (reason === "inactive") {
        goToInvalid("inactive");
        return;
      }
      if (reason === "invalid") {
        goToInvalid("not_found");
        return;
      }
      setJoinError(t("joinError"));
    }
  }, [enroll, goTo, goToInvalid, state.code, t]);

  const resetToCode = useCallback(() => {
    setSubmitError(null);
    setJoinError(null);
    setState(INITIAL_STATE);
    lookup.reset();
    enroll.reset();
  }, [enroll, lookup]);

  const backToCourses = useCallback(() => {
    router.push("/student/courses");
  }, [router]);

  const openCourse = useCallback(() => {
    // The per-course workspace route is not built in this phase; land the
    // student on their courses list (the joined, active course now appears
    // there) rather than a `/student/courses/{id}` 404.
    router.push("/student/courses");
  }, [router]);

  const goToDashboard = useCallback(() => {
    router.push("/student/dashboard");
  }, [router]);

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <PageHeader title={t("title")} description={t("subtitle")} />

      {state.step === "code" ? (
        <StepCodeEntry
          onSubmit={handleCodeSubmit}
          isSubmitting={lookup.isPending}
          submitError={submitError}
          initialCode={initialCode}
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
          onJoin={handleJoin}
          onBack={() => goTo("deep_preview")}
          isJoining={enroll.isPending}
          joinError={joinError}
        />
      ) : state.step === "success" ? (
        <StateJoinSuccess
          courseName={state.courseName}
          onOpenCourse={openCourse}
          onDashboard={goToDashboard}
        />
      ) : state.step === "pending" ? (
        <StatePendingApproval
          courseName={state.courseName}
          onBackToCourses={backToCourses}
        />
      ) : state.step === "not_open" ? (
        <StateCourseNotOpen
          courseName={state.courseName || state.lookup?.name || ""}
          onTryAgain={resetToCode}
          onBackToCourses={backToCourses}
        />
      ) : (
        <StepCodeEntry
          onSubmit={handleCodeSubmit}
          isSubmitting={lookup.isPending}
          submitError={submitError}
        />
      )}
    </div>
  );
}
