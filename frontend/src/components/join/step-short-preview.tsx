"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCoursePreview } from "@/hooks/use-readiness";

interface StepShortPreviewProps {
  readonly courseId: string;
  readonly code: string;
  /** Advance to the eligibility survey (S006). */
  readonly onStart: () => void;
  /** Return to S003 to enter a different code. */
  readonly onBack: () => void;
}

/**
 * S005 — short course preview. Renders the code-gated short preview
 * (`useCoursePreview` depth=`short`): the course name, language, and teaser
 * description the teacher published. "Start readiness" advances to the
 * eligibility survey. If the course is not open yet, we surface that inline
 * (the server re-checks the setup gate at the actual join, so this is a
 * courtesy signal, not the enforcement point).
 */
export function StepShortPreview({
  courseId,
  code,
  onStart,
  onBack,
}: StepShortPreviewProps) {
  const t = useTranslations("student.join");
  const preview = useCoursePreview(courseId, code, "short");

  if (preview.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-2/3" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-10 w-40" />
      </div>
    );
  }

  if (preview.isError || !preview.data) {
    return (
      <div className="space-y-6">
        <StateBanner
          tone="warning"
          title={t("shortPreview.errorTitle")}
          reason={t("shortPreview.errorReason")}
        />
        <Button type="button" variant="outline" size="lg" onClick={onBack}>
          {t("shortPreview.back")}
        </Button>
      </div>
    );
  }

  const course = preview.data;

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-[var(--color-text-muted)]">
            {t("shortPreview.eyebrow")}
          </p>
          <h2 className="text-[20px] font-semibold leading-tight tracking-tight text-[var(--color-text)]">
            {course.name}
          </h2>
          <p className="text-[13px] text-[var(--color-text-muted)]">
            {t("shortPreview.language", { language: course.language })}
          </p>
        </div>

        {course.description ? (
          <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {course.description}
          </p>
        ) : (
          <p className="text-[14px] italic leading-relaxed text-[var(--color-text-muted)]">
            {t("shortPreview.noDescription")}
          </p>
        )}
      </div>

      {course.is_open ? null : (
        <StateBanner
          tone="info"
          title={t("shortPreview.notOpenTitle")}
          reason={t("shortPreview.notOpenReason")}
        />
      )}

      <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
        <Button type="button" variant="outline" size="lg" onClick={onBack}>
          {t("shortPreview.back")}
        </Button>
        <Button type="button" size="lg" onClick={onStart}>
          {t("shortPreview.start")}
        </Button>
      </div>
    </div>
  );
}
