"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { PageHeader, StateBanner, StepWizard, type WizardStep } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { StepBasics } from "@/components/setup/step-basics";
import { StepSyllabus } from "@/components/setup/step-syllabus";
import { StepMaterials } from "@/components/setup/step-materials";
import {
  SETUP_STEP_KEYS,
  useSetupState,
  type SetupState,
  type SetupStepKey,
} from "@/hooks/use-setup";

/** Steps that already have wizard content this phase (P1 Tasks 12–13). */
const IMPLEMENTED_STEPS: ReadonlySet<SetupStepKey> = new Set([
  "basics",
  "syllabus",
  "materials",
]);

function isStepKey(value: string | null): value is SetupStepKey {
  return value !== null && (SETUP_STEP_KEYS as readonly string[]).includes(value);
}

function firstIncomplete(state: SetupState | undefined): SetupStepKey {
  if (!state) return "basics";
  return SETUP_STEP_KEYS.find((key) => !state.steps[key]) ?? "basics";
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
  const currentId: SetupStepKey = isStepKey(paramStep) ? paramStep : firstIncomplete(state);

  const goToStep = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("step", id);
      router.push(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const currentIndex = SETUP_STEP_KEYS.indexOf(currentId);

  const handleBack = useCallback(() => {
    if (currentIndex > 0) goToStep(SETUP_STEP_KEYS[currentIndex - 1]);
  }, [currentIndex, goToStep]);

  const handleNext = useCallback(() => {
    if (currentIndex >= 0 && currentIndex < SETUP_STEP_KEYS.length - 1) {
      goToStep(SETUP_STEP_KEYS[currentIndex + 1]);
    }
  }, [currentIndex, goToStep]);

  const steps: WizardStep[] = useMemo(
    () =>
      SETUP_STEP_KEYS.map((key) => ({
        id: key,
        label: t(`steps.${key}`),
        complete: Boolean(state?.steps[key]),
        blocked: !IMPLEMENTED_STEPS.has(key) && key !== currentId,
      })),
    [state, t, currentId]
  );

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
          total: SETUP_STEP_KEYS.length,
        })}
      >
        {currentId === "basics" ? (
          <StepBasics courseId={courseId} onComplete={handleNext} />
        ) : currentId === "syllabus" ? (
          <StepSyllabus courseId={courseId} onComplete={handleNext} />
        ) : currentId === "materials" ? (
          <StepMaterials courseId={courseId} onComplete={handleNext} />
        ) : (
          <StateBanner
            tone="waiting"
            title={t(`steps.${currentId}`)}
            reason={t("wizard.comingSoon")}
          />
        )}
      </StepWizard>
    </div>
  );
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
