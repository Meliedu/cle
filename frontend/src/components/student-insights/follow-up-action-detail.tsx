"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, Check, Eye, RotateCcw } from "lucide-react";

import { PageHeader, StateBanner } from "@/components/patterns";
import { StatusChip, type StatusTone } from "@/components/course/session-status";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useFollowUpDetail,
  useMarkFollowUpViewed,
  type OutcomeStatus,
} from "@/hooks/use-follow-ups";

import { SignalDetail } from "./signal-detail";

interface FollowUpActionDetailProps {
  readonly courseId: string;
  readonly followUpId: string;
}

/** Outcome ("did it move") status → one shared status-chip tone. */
function outcomeTone(status: OutcomeStatus): StatusTone {
  switch (status) {
    case "improved":
    case "resolved":
      return "success";
    case "completed":
      return "info";
    case "persistent":
    case "needs_review":
      return "progress";
    case "carried_forward":
      return "muted";
    case "pending":
    default:
      return "neutral";
  }
}

/**
 * S061 — student follow-up action detail. Reads one `FollowUpAction` merged with
 * its linked note's REVIEWED fields (`useFollowUpDetail`). While
 * `waiting_for_review`, only the designed waiting banner shows — never an
 * unreviewed AI draft's content (Core §0.2, Decision 6). A reviewed follow-up
 * shows the observed signal + instructor interpretation + limitation, the
 * "did it move" outcome, a mark-viewed action, the source provenance, and — when
 * a revisit link exists — a CTA into the P3 checkpoint revisit flow.
 */
export function FollowUpActionDetail({
  courseId,
  followUpId,
}: FollowUpActionDetailProps) {
  const t = useTranslations("student.followUp");
  const { data: detail, isLoading, isError } = useFollowUpDetail(followUpId);
  const markViewed = useMarkFollowUpViewed();

  const backHref = `/student/courses/${courseId}/checklist`;
  const backLink = (
    <Link
      href={backHref}
      className="inline-flex items-center gap-1.5 hover:text-[var(--color-text)]"
    >
      <ArrowLeft aria-hidden="true" className="size-3.5" />
      {t("backToChecklist")}
    </Link>
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-32 w-full rounded-[var(--radius-xl)]" />
        <Skeleton className="h-24 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (isError || !detail) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("title")} breadcrumb={backLink} />
        <StateBanner
          tone="warning"
          title={t("error.title")}
          reason={t("error.reason")}
        />
      </div>
    );
  }

  // Designed waiting-for-instructor-feedback state (S071): no AI content.
  if (detail.waiting_for_review) {
    return (
      <div className="space-y-6">
        <PageHeader title={t("title")} breadcrumb={backLink} />
        <StateBanner
          tone="waiting"
          title={t("waiting.title")}
          reason={t("waiting.reason")}
        />
      </div>
    );
  }

  const alreadyViewed =
    detail.assignment_status === "viewed" ||
    detail.assignment_status === "completed" ||
    detail.assignment_status === "checked" ||
    detail.assignment_status === "closed";

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        breadcrumb={backLink}
      />

      <div className="space-y-4">
        {detail.observed_signal ? (
          <Field label={t("observedSignal")} value={detail.observed_signal} />
        ) : null}
        {detail.draft_interpretation ? (
          <Field
            label={t("interpretation")}
            value={detail.draft_interpretation}
          />
        ) : null}
        {detail.limitation_note ? (
          <Field
            label={t("limitation")}
            value={detail.limitation_note}
            muted
          />
        ) : null}
      </div>

      {detail.outcome_status ? (
        <div className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
          <span className="text-[13px] font-medium text-[var(--color-text-secondary)]">
            {t("outcome.label")}
          </span>
          <StatusChip
            tone={outcomeTone(detail.outcome_status)}
            label={t(`outcome.${detail.outcome_status}`)}
          />
        </div>
      ) : null}

      {detail.revisit !== null ? (
        <StateBanner
          tone="info"
          title={t("revisit.title")}
          reason={t("revisit.reason")}
          action={
            <Link
              href={detail.revisit.revisit_path}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-primary)] px-3 text-[13px] font-semibold text-[var(--color-text-on-primary)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-primary-hover)]"
            >
              <RotateCcw aria-hidden="true" className="size-4" />
              {t("revisit.cta")}
            </Link>
          }
        />
      ) : null}

      <SignalDetail signalId={detail.learning_note_id} />

      <div className="flex items-center gap-3 pt-2">
        {alreadyViewed ? (
          <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-success)]">
            <Check aria-hidden="true" className="size-4" />
            {t("viewed")}
          </span>
        ) : (
          <button
            type="button"
            onClick={() => markViewed.mutate(followUpId)}
            disabled={markViewed.isPending}
            className="inline-flex min-h-11 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-[14px] font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] disabled:opacity-60"
          >
            <Eye aria-hidden="true" className="size-4" />
            {markViewed.isPending ? t("marking") : t("markViewed")}
          </button>
        )}
      </div>
    </div>
  );
}

interface FieldProps {
  readonly label: string;
  readonly value: string;
  readonly muted?: boolean;
}

/** One reviewed-note field: an uppercase label + its body copy. */
function Field({ label, value, muted }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <h2 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </h2>
      <p
        className={
          muted
            ? "text-[13px] leading-relaxed text-[var(--color-text-secondary)]"
            : "text-[15px] leading-relaxed text-[var(--color-text)]"
        }
      >
        {value}
      </p>
    </div>
  );
}
