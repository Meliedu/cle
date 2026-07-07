"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, CircleAlert, Loader2, Rocket, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, StateBanner } from "@/components/patterns";
import { SetupPublishSuccess } from "@/components/setup/setup-publish-success";
import { SetupMissingSourceError } from "@/components/setup/setup-missing-source-error";
import {
  SETUP_STEP_KEYS,
  setupErrorCode,
  usePublishSetup,
  useSetupAnalysis,
  useSetupState,
  type SetupStepKey,
} from "@/hooks/use-setup";

interface StepReviewProps {
  readonly courseId: string;
  /** Jump back to a wizard step to finish or edit it. */
  readonly onNavigate?: (step: SetupStepKey) => void;
}

/**
 * T026 — setup-review-checklist. The terminal wizard screen (after `class_code`).
 * It is NOT a `SETUP_STEP_KEYS` entry: publishing is the action, not a checklist
 * flag. It summarizes all nine setup steps with done/missing status (from
 * `useSetupState`), lets the teacher jump back to any incomplete step, and
 * publishes via `usePublishSetup` (Decision 1: flips `setup_status='published'`
 * + `context_status='approved'`). On success it swaps to `SetupPublishSuccess`
 * (T027); on `409 SETUP_INCOMPLETE` it swaps to `SetupMissingSourceError` (T028)
 * listing what's still missing. The latest analyzer `missing_sources` are folded
 * into the blocked state so ungrounded outcomes/sessions surface there too.
 */
export function StepReview({ courseId, onNavigate }: StepReviewProps) {
  const t = useTranslations("teacher.setup.review");
  const { data: state, isLoading } = useSetupState(courseId);
  const { data: analysis } = useSetupAnalysis(courseId);
  const publish = usePublishSetup(courseId);

  const [blocked, setBlocked] = useState(false);
  const [justPublished, setJustPublished] = useState(false);
  const [publishError, setPublishError] = useState<string | null>(null);

  const missingSources = analysis?.analysis?.missing_sources ?? [];
  const hasMissingSources = Boolean(analysis?.analysis?.has_missing_sources);

  // `justPublished` shows the success screen immediately on a successful mutation
  // without waiting for the setup-state cache to repopulate; a course that was
  // already published (revisit) is detected from the server state.
  const published =
    justPublished ||
    (state?.setup_status === "published" && state?.context_status === "approved");

  const showCode = useCallback(() => onNavigate?.("class_code"), [onNavigate]);

  const doPublish = useCallback(async () => {
    setPublishError(null);
    try {
      await publish.mutateAsync();
      setJustPublished(true);
    } catch (error) {
      if (setupErrorCode(error) === "SETUP_INCOMPLETE") {
        setBlocked(true);
        return;
      }
      setPublishError(t("publishError"));
    }
  }, [publish, t]);

  if (isLoading || !state) {
    return <EmptyState variant="waiting" title={t("title")} />;
  }

  if (published) {
    return <SetupPublishSuccess courseId={courseId} onShowCode={showCode} />;
  }

  if (blocked) {
    return (
      <SetupMissingSourceError
        missingSteps={state.missing}
        missingSources={missingSources}
        onNavigate={onNavigate}
        onBack={() => setBlocked(false)}
      />
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        {hasMissingSources ? (
          <StateBanner
            tone="warning"
            title={t("title")}
            reason={t("subtitle")}
            action={
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setBlocked(true)}
              >
                {t("fix")}
              </Button>
            }
          />
        ) : null}

        <div className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          <p className="border-b border-[var(--color-border)] px-4 py-3 text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("checklistTitle")}
          </p>
          <ul>
            {SETUP_STEP_KEYS.map((key) => (
              <ChecklistRow
                key={key}
                stepKey={key}
                done={Boolean(state.steps[key])}
                onNavigate={onNavigate}
                t={t}
              />
            ))}
          </ul>
        </div>

        {publishError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {publishError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={publish.isPending}
            onClick={() => void doPublish()}
          >
            {publish.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Rocket aria-hidden="true" />
            )}
            {publish.isPending ? t("publishing") : t("publish")}
          </Button>
        </div>
      </div>

      <AfterPublishAside t={t} />
    </div>
  );
}

interface ChecklistRowProps {
  readonly stepKey: SetupStepKey;
  readonly done: boolean;
  readonly onNavigate?: (step: SetupStepKey) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function ChecklistRow({ stepKey, done, onNavigate, t }: ChecklistRowProps) {
  const ts = useTranslations("teacher.setup");
  return (
    <li className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 items-start gap-3">
        <span
          aria-hidden="true"
          className={
            done
              ? "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-success)] text-[var(--color-on-accent)]"
              : "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-[var(--color-warning)]/50 bg-[var(--color-warning-light)] text-[var(--color-warning)]"
          }
        >
          {done ? (
            <Check className="size-3" strokeWidth={2.5} />
          ) : (
            <CircleAlert className="size-3" strokeWidth={2.2} />
          )}
        </span>
        <div className="min-w-0 space-y-0.5">
          <p className="text-[13px] font-medium text-[var(--color-text)]">
            {ts(`steps.${stepKey}`)}
          </p>
          <p className="text-[12px] leading-snug text-[var(--color-text-secondary)]">
            {t(`stepDesc.${stepKey}`)}
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-2.5">
        <Badge variant={done ? "secondary" : "outline"}>
          {done ? t("statusComplete") : t("statusMissing")}
        </Badge>
        {onNavigate ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => onNavigate(stepKey)}
          >
            {done ? t("edit") : t("fix")}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function AfterPublishAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const points = ["joinCode", "calendar", "materials"] as const;
  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("afterPublish.title")}
      </p>
      <ul className="mt-4 space-y-3">
        {points.map((point) => (
          <li key={point} className="flex gap-2.5">
            <Sparkles
              aria-hidden="true"
              strokeWidth={1.85}
              className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
            />
            <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
              {t(`afterPublish.${point}`)}
            </p>
          </li>
        ))}
      </ul>
    </aside>
  );
}
