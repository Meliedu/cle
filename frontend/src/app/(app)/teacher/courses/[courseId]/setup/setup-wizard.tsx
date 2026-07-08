"use client";

import { useCallback, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner, StepWizard, type WizardStep } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { StepBasics } from "@/components/setup/step-basics";
import { StepSyllabus } from "@/components/setup/step-syllabus";
import { StepMaterials } from "@/components/setup/step-materials";
import { StepSchedule } from "@/components/setup/step-schedule";
import { StepSessions } from "@/components/setup/step-sessions";
import { StepAnalyzer } from "@/components/setup/step-analyzer";
import { StepIlo } from "@/components/setup/step-ilo";
import { StepCheckpoints } from "@/components/setup/step-checkpoints";
import { StepScorePolicy } from "@/components/setup/step-score-policy";
import { StepClassCode } from "@/components/setup/step-class-code";
import { StepMemoryImport } from "@/components/setup/step-memory-import";
import { StepReview } from "@/components/setup/step-review";
import {
  SETUP_STEP_KEYS,
  useSetupState,
  type SetupState,
  type SetupStepKey,
} from "@/hooks/use-setup";

/**
 * The wizard's terminal screen: a review-and-publish checklist. It is NOT a
 * `SETUP_STEP_KEYS` flag (there are exactly 9 step flags, basics..class_code) —
 * publishing is the action, not a checklist item — so it lives here as an extra
 * rail entry appended after `class_code`. T027 (success) / T028 (blocked) are
 * states of this same screen, owned by `StepReview`.
 */
const REVIEW_ID = "review";

/** Ordered wizard screens: the 9 step flags plus the terminal review screen. */
const WIZARD_IDS: readonly string[] = [...SETUP_STEP_KEYS, REVIEW_ID];

/** Steps that already have wizard content this phase (P1 Tasks 12–16). */
const IMPLEMENTED_STEPS: ReadonlySet<SetupStepKey> = new Set([
  "basics",
  "syllabus",
  "materials",
  "schedule",
  "analyzer_review",
  "ilo_map",
  "checkpoints",
  "score_policy",
  "class_code",
]);

function isWizardId(value: string | null): value is string {
  return value !== null && WIZARD_IDS.includes(value);
}

function isPublished(state: SetupState | undefined): boolean {
  return (
    state?.setup_status === "published" && state?.context_status === "approved"
  );
}

function firstIncomplete(state: SetupState | undefined): string {
  if (!state) return "basics";
  // A published course lands on the review/success screen; otherwise the first
  // outstanding step, falling back to review once every step is done.
  if (isPublished(state)) return REVIEW_ID;
  return SETUP_STEP_KEYS.find((key) => !state.steps[key]) ?? REVIEW_ID;
}

interface SetupWizardProps {
  readonly courseId: string;
}

/**
 * Client orchestrator for the course-setup wizard. Reads the server-owned
 * checklist (`useSetupState`), derives the `StepWizard` rail from
 * `SETUP_STEP_KEYS`, and renders the active step's content. The active step is
 * driven by the `?step=` query param (defaulting to the first incomplete step).
 * Only the basics step ships content this phase; later steps render a
 * "coming soon" placeholder until Tasks 13–16 fill them in.
 */
export function SetupWizard({ courseId }: SetupWizardProps) {
  const t = useTranslations("teacher.setup");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const { data: state, isLoading, isError, refetch } = useSetupState(courseId);

  const paramStep = searchParams.get("step");
  const currentId: string = isWizardId(paramStep) ? paramStep : firstIncomplete(state);

  const goToStep = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("step", id);
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const currentIndex = WIZARD_IDS.indexOf(currentId);

  const handleBack = useCallback(() => {
    if (currentIndex > 0) goToStep(WIZARD_IDS[currentIndex - 1]);
  }, [currentIndex, goToStep]);

  const handleNext = useCallback(() => {
    if (currentIndex >= 0 && currentIndex < WIZARD_IDS.length - 1) {
      goToStep(WIZARD_IDS[currentIndex + 1]);
    }
  }, [currentIndex, goToStep]);

  const steps: WizardStep[] = useMemo(() => {
    const stepFlags: WizardStep[] = SETUP_STEP_KEYS.map((key) => ({
      id: key,
      label: t(`steps.${key}`),
      complete: Boolean(state?.steps[key]),
      blocked: !IMPLEMENTED_STEPS.has(key) && key !== currentId,
    }));
    return [
      ...stepFlags,
      {
        id: REVIEW_ID,
        label: t("steps.review"),
        // The terminal screen reads complete once the course is published; before
        // that it stays navigable via Next (or the rail once every step is done).
        complete: isPublished(state) || (state?.missing.length === 0 && !!state),
        blocked: false,
      },
    ];
  }, [state, t, currentId]);

  if (isLoading) {
    return <SetupWizardSkeleton />;
  }

  if (isError || !state) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <PageHeader title={t("title")} description={t("wizard.subtitle")} />
        <StateBanner
          tone="warning"
          title={t("wizard.loadErrorTitle")}
          reason={t("wizard.loadError")}
          action={
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-[var(--radius-md)] border border-[var(--color-border)] px-3 py-1.5 text-[13px] font-medium text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)]"
            >
              {t("wizard.retry")}
            </button>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader
        title={t("title")}
        description={t("wizard.subtitle")}
        breadcrumb={
          <Link
            href="/teacher/courses"
            className="rounded-[var(--radius-sm)] transition-colors hover:text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            {t("wizard.breadcrumb")}
          </Link>
        }
      />

      <StepWizard
        steps={steps}
        currentId={currentId}
        onStepSelect={goToStep}
        onBack={handleBack}
        onNext={handleNext}
        backLabel={t("wizard.back")}
        nextLabel={t("wizard.next")}
        progressLabel={t("wizard.progress", {
          current: currentIndex + 1,
          total: WIZARD_IDS.length,
        })}
      >
        {currentId === "basics" ? (
          <StepBasics courseId={courseId} onComplete={handleNext} />
        ) : currentId === "syllabus" ? (
          <StepSyllabus courseId={courseId} onComplete={handleNext} />
        ) : currentId === "materials" ? (
          <StepMaterials courseId={courseId} onComplete={handleNext} />
        ) : currentId === "schedule" ? (
          <ScheduleStep courseId={courseId} onComplete={handleNext} />
        ) : currentId === "analyzer_review" ? (
          <StepAnalyzer
            courseId={courseId}
            onComplete={handleNext}
            onNavigate={goToStep}
          />
        ) : currentId === "ilo_map" ? (
          <StepIlo courseId={courseId} onComplete={handleNext} />
        ) : currentId === "checkpoints" ? (
          <StepCheckpoints courseId={courseId} onComplete={handleNext} />
        ) : currentId === "score_policy" ? (
          <StepScorePolicy courseId={courseId} onComplete={handleNext} />
        ) : currentId === "class_code" ? (
          <div className="space-y-8">
            <StepClassCode courseId={courseId} onComplete={handleNext} />
            {/*
              T023 previous-term memory import is not a `SETUP_STEP_KEYS` entry —
              it never gates publish. It surfaces here as a skippable prior-term
              carry-forward picker; it self-hides to an empty state when this
              course has no earlier offering to import from.
            */}
            <StepMemoryImport courseId={courseId} />
          </div>
        ) : currentId === REVIEW_ID ? (
          <StepReview courseId={courseId} onNavigate={goToStep} />
        ) : null}
      </StepWizard>
    </div>
  );
}

interface ScheduleStepProps {
  readonly courseId: string;
  readonly onComplete: () => void;
}

/**
 * The `schedule` wizard step is two Figma screens under one `SETUP_STEP_KEYS`
 * entry: T018 (schedule-and-venue editor, `StepSchedule`) then T021
 * (session-generation-review, `StepSessions`). There is deliberately no separate
 * `sessions` step key — the editor flips the `schedule` flag, and the review is
 * an informational confirm that folds under it. "Edit sessions" returns to the
 * editor; "Approve sessions" advances the wizard.
 */
function ScheduleStep({ courseId, onComplete }: ScheduleStepProps) {
  const [phase, setPhase] = useState<"edit" | "review">("edit");

  if (phase === "review") {
    return (
      <StepSessions
        courseId={courseId}
        onEdit={() => setPhase("edit")}
        onComplete={onComplete}
      />
    );
  }
  return <StepSchedule courseId={courseId} onComplete={() => setPhase("review")} />;
}

function SetupWizardSkeleton() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="space-y-2">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="flex flex-col gap-8 md:flex-row md:gap-10">
        <div className="space-y-2 md:w-64 md:shrink-0">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-10 rounded-[var(--radius-lg)]" />
          ))}
        </div>
        <div className="flex-1 space-y-4">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-64 rounded-[var(--radius-lg)]" />
        </div>
      </div>
    </div>
  );
}
