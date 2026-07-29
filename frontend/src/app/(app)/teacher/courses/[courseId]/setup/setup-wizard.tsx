"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useUrlState } from "@/hooks/use-url-state";
import { useDocuments } from "@/hooks/use-documents";
import { documentReadiness } from "@/lib/teaching-day";
import { rollUpSources } from "@/lib/contracts/state";
import {
  firstIncompleteStage,
  SETUP_STAGES,
  stageIsReachable,
  stageProgress,
  stageStatuses,
  type SetupStage,
} from "@/lib/setup-stages";
import { StageStepper } from "@/components/setup/stage-stepper";
import { SetupContextRail } from "@/components/setup/setup-context-rail";
import type { SourceRow } from "@/components/setup/source-status-list";
import { StageBasics } from "@/components/setup/stage-basics";
import { StageSources } from "@/components/setup/stage-sources";
import { StageSchedule } from "@/components/setup/stage-schedule";
import { StageReview } from "@/components/setup/stage-review";
import { StagePublish } from "@/components/setup/stage-publish";
import { useSetupState } from "@/hooks/use-setup";

function isStage(value: string | null): value is SetupStage {
  return value !== null && (SETUP_STAGES as readonly string[]).includes(value);
}

interface SetupWizardProps {
  readonly courseId: string;
}

/**
 * The course-setup wizard (Plate 05).
 *
 * Four changes from the ten-step version:
 *
 *   rule 1  Five user-facing stages replace ten implementation steps. The nine
 *           backend step flags are unchanged and still gate publish; they are
 *           now sub-state inside a stage rather than top-level destinations.
 *   rule 2  "Setup owns the working surface while the course is incomplete."
 *           The course rail is suppressed here (see `Sidebar`), leaving only
 *           global context and a safe exit.
 *   rule 3  Failures are typed and user-safe, with the failing source named
 *           and Retry/Replace offered. Nothing on this surface can render a
 *           backend exception.
 *   rule 4  One dominant continue action, derived from readiness. Provenance
 *           and safe-to-leave status stay visible throughout.
 *
 * Stage selection lives in the URL so a refresh, a Back, or a shared link all
 * land on the same stage.
 */
export function SetupWizard({ courseId }: SetupWizardProps) {
  const t = useTranslations("teacher.setup");
  const router = useRouter();
  const url = useUrlState();

  const { data: state, isLoading, isError, refetch } = useSetupState(courseId);
  const documents = useDocuments(courseId);

  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  /**
   * The stage actually shown.
   *
   * A URL stage is honoured only if it is REACHABLE. The stepper disables a
   * locked stage's button, but that alone does not gate the route: typing
   * `?stage=publish` on a brand-new course rendered the publish screen with
   * every prerequisite outstanding. Gating has to hold regardless of how the
   * user arrived, so an unreachable stage falls back to the frontier.
   */
  const stageParam = url.get("stage");
  const requested: SetupStage | null = isStage(stageParam) ? stageParam : null;
  const current: SetupStage =
    requested && stageIsReachable(requested, state)
      ? requested
      : firstIncompleteStage(state);

  const goToStage = useCallback(
    (stage: SetupStage) => url.set("stage", stage),
    [url]
  );

  /**
   * Autosave acknowledgement. Stage content calls this after a successful
   * write so the header can say when work was last persisted, which is what
   * makes "safe to leave" credible rather than a claim.
   */
  const handleSaved = useCallback(() => setLastSavedAt(new Date()), []);

  const handleAdvance = useCallback(() => {
    const index = SETUP_STAGES.indexOf(current);
    if (index < SETUP_STAGES.length - 1) goToStage(SETUP_STAGES[index + 1]);
  }, [current, goToStage]);

  const sources: readonly SourceRow[] = useMemo(
    () =>
      (documents.data ?? []).map((document) => ({
        id: document.id,
        name: document.filename,
        readiness: documentReadiness(document.status),
        // No progress number. The backend reports a status, not a percentage,
        // so any figure here is invented: every processing source claimed
        // exactly 62%, including one stuck for ten minutes. The readiness word
        // carries the meaning; the bar renders indeterminate.
        progress: null,
        // The backend serves a typed code; a legacy row without one falls back
        // to generic safe copy rather than to any stored message.
        errorCode: document.error_code ?? null,
      })),
    [documents.data]
  );

  const rollup = useMemo(
    () => rollUpSources(sources.map((source) => source.readiness)),
    [sources]
  );

  const statuses = useMemo(
    () => stageStatuses(state, current),
    [state, current]
  );
  const reachable = useMemo(() => {
    const result = {} as Record<SetupStage, boolean>;
    for (const stage of SETUP_STAGES) {
      result[stage] = stageIsReachable(stage, state);
    }
    return result;
  }, [state]);
  const progress = useMemo(() => {
    const result = {} as Record<SetupStage, { done: number; total: number }>;
    for (const stage of SETUP_STAGES) {
      const { done, total } = stageProgress(stage, state?.steps ?? {});
      result[stage] = { done, total };
    }
    return result;
  }, [state]);

  if (isLoading) return <SetupSkeleton />;

  if (isError || !state) {
    return (
      <div className="mx-auto max-w-5xl px-6 py-8 md:px-10">
        <StateBanner
          tone="warning"
          title={t("wizard.loadErrorTitle")}
          reason={t("wizard.loadError")}
          action={
            <Button size="xl" variant="outline" onClick={() => void refetch()}>
              {t("wizard.retry")}
            </Button>
          }
        />
      </div>
    );
  }

  /**
   * Autosave acknowledgement.
   *
   * "Saved just now" is claimed ONLY after a write this session actually
   * succeeded. Work carried over from an earlier session says "Saved" without
   * a time, because `SetupState` carries no timestamp and asserting "just now"
   * for week-old progress would be false. A course with nothing done yet says
   * nothing at all.
   */
  const anyStepDone = Object.values(state.steps).some(Boolean);
  const savedLabel = lastSavedAt
    ? t("savedJustNow")
    : anyStepDone
      ? t("saved")
      : null;

  return (
    <div className="mx-auto w-full max-w-[1240px] px-6 py-8 md:px-10">
      {/* Global context + safe exit. No course rail, no course tabs: setup owns
          the surface while the course is incomplete. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav aria-label="Breadcrumb">
          <ol className="flex items-center gap-1.5 text-[13px] text-[var(--color-text-muted)]">
            <li>
              <Link
                href="/teacher/courses"
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-sm)] outline-none transition-colors hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                <ArrowLeft aria-hidden="true" className="size-3.5" />
                {t("backToCourses")}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li className="font-medium text-[var(--color-text-secondary)]">
              {t("setupBreadcrumb")}
            </li>
          </ol>
        </nav>

        {savedLabel ? (
          <p
            aria-live="polite"
            className="text-[13px] text-[var(--color-text-muted)]"
          >
            {savedLabel}
          </p>
        ) : null}
      </div>

      <header className="mt-4">
        <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)]">
          {t(`stageTitle.${current}`)}
        </h1>
        <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
          {t("processingContinues")}
        </p>
      </header>

      <div className="mt-7 border-b border-[var(--color-border)] pb-6">
        <StageStepper
          statuses={statuses}
          reachable={reachable}
          progress={progress}
          onSelect={goToStage}
        />
      </div>

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="min-w-0">
          {current === "basics" ? (
            <StageBasics
              courseId={courseId}
              onSaved={handleSaved}
              onAdvance={handleAdvance}
            />
          ) : current === "sources" ? (
            <StageSources
              courseId={courseId}
              sources={sources}
              isLoading={documents.isLoading}
              onSaved={handleSaved}
              onAdvance={handleAdvance}
            />
          ) : current === "schedule" ? (
            <StageSchedule
              courseId={courseId}
              onSaved={handleSaved}
              onAdvance={handleAdvance}
            />
          ) : current === "review" ? (
            <StageReview
              courseId={courseId}
              onSaved={handleSaved}
              onAdvance={handleAdvance}
            />
          ) : (
            <StagePublish courseId={courseId} onNavigate={goToStage} />
          )}

          {/* The safe exit. Always present, never destructive. */}
          <div className="mt-8 flex justify-end border-t border-[var(--color-border)] pt-6">
            <button
              type="button"
              onClick={() => router.push("/teacher/courses")}
              className="inline-flex h-11 items-center rounded-[var(--radius-md)] px-3 text-[14px] font-medium text-[var(--color-text-secondary)] outline-none transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
            >
              {t("saveAndLeave")}
            </button>
          </div>
        </div>

        {/*
          `lastCheckedAt` is the real moment this client last read source state,
          which is what "Last checked" claims. Passing a hardcoded "just now"
          would have made the rail assert freshness it could not know.
        */}
        <SetupContextRail
          sources={sources}
          rollup={rollup}
          lastCheckedAt={documents.dataUpdatedAt ?? null}
        />
      </div>
    </div>
  );
}

function SetupSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1240px] px-6 py-8 md:px-10">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="mt-4 h-9 w-72" />
      <Skeleton className="mt-2 h-4 w-96" />
      <Skeleton className="mt-7 h-12 w-full" />
      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
        <Skeleton className="h-[320px] rounded-[var(--radius-xl)]" />
        <Skeleton className="h-[240px] rounded-[var(--radius-xl)]" />
      </div>
    </div>
  );
}
