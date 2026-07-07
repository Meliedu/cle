"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCoursePreview } from "@/hooks/use-readiness";
import { ApiError } from "@/lib/api";

interface StepDeepPreviewProps {
  readonly courseId: string;
  readonly code: string;
  /** Advance the funnel to the readiness summary (S011). */
  readonly onContinue: () => void;
  /** Return to the recommendation (S009). */
  readonly onBack?: () => void;
}

/** Safely read a non-negative integer count off the untyped `detail` blob. */
function readCount(
  detail: Record<string, unknown> | null | undefined,
  key: string
): number {
  const value = detail?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/**
 * S010 — deep course preview. Fetches the fuller, code-gated teaser
 * (`useCoursePreview` depth=`deep`) and shows the published session + objective
 * counts. The deep preview shares the join gate (Decision 3): if the course is
 * not open yet the endpoint returns `SETUP_NOT_OPEN` (409), which we surface as
 * the not-open state (S012 territory, scoped here to the deep-preview-blocked
 * case) rather than a broken teaser. Either way the student can continue to the
 * readiness summary — the deep preview never blocks.
 */
export function StepDeepPreview({
  courseId,
  code,
  onContinue,
  onBack,
}: StepDeepPreviewProps) {
  const t = useTranslations("student.join");
  const preview = useCoursePreview(courseId, code, "deep");

  if (preview.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-10 w-40" />
      </div>
    );
  }

  const notOpen =
    preview.error instanceof ApiError &&
    preview.error.code === "SETUP_NOT_OPEN";

  if (notOpen) {
    return (
      <div className="space-y-6">
        <StateBanner
          tone="info"
          title={t("deepPreview.notOpenTitle")}
          reason={t("deepPreview.notOpenReason")}
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
          {onBack ? (
            <Button type="button" variant="outline" size="lg" onClick={onBack}>
              {t("deepPreview.back")}
            </Button>
          ) : (
            <span />
          )}
          <Button type="button" size="lg" onClick={onContinue}>
            {t("deepPreview.continue")}
          </Button>
        </div>
      </div>
    );
  }

  if (preview.isError || !preview.data) {
    return (
      <div className="space-y-6">
        <StateBanner
          tone="warning"
          title={t("deepPreview.errorTitle")}
          reason={t("deepPreview.errorReason")}
        />
        <Button type="button" variant="outline" size="lg" onClick={onContinue}>
          {t("deepPreview.continue")}
        </Button>
      </div>
    );
  }

  const course = preview.data;
  const sessions = readCount(course.detail, "sessions");
  const objectives = readCount(course.detail, "objectives");

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            {t("deepPreview.eyebrow")}
          </p>
          <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
            {course.name}
          </h2>
        </div>

        <dl className="grid grid-cols-2 gap-3">
          <div className="space-y-1 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4">
            <dt className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
              {t("deepPreview.sessions")}
            </dt>
            <dd className="text-[22px] font-semibold tabular-nums text-[var(--color-text)]">
              {sessions}
            </dd>
          </div>
          <div className="space-y-1 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4">
            <dt className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
              {t("deepPreview.objectives")}
            </dt>
            <dd className="text-[22px] font-semibold tabular-nums text-[var(--color-text)]">
              {objectives}
            </dd>
          </div>
        </dl>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        {onBack ? (
          <Button type="button" variant="outline" size="lg" onClick={onBack}>
            {t("deepPreview.back")}
          </Button>
        ) : (
          <span />
        )}
        <Button type="button" size="lg" onClick={onContinue}>
          {t("deepPreview.continue")}
        </Button>
      </div>
    </div>
  );
}
