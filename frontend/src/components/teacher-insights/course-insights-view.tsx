"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  AlertTriangle,
  ChevronRight,
  GraduationCap,
  Inbox,
  Users,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useCourseInsights } from "@/hooks/use-insights";

import { EffectivenessTracker } from "./effectiveness-tracker";
import { SignalDetailDrawer } from "./signal-detail-drawer";
import { useCourseSignals, type TeacherSignal } from "./use-teacher-signals";
import { InsightCard, ProgressBar, StatTile } from "./insights-primitives";
import {
  formatFraction,
  barWidth,
  isPendingReview,
  reviewStatusToneClass,
} from "./insights-format";

/**
 * T076 — teacher course insights. RESHAPES the pure-read insights payload
 * (`useCourseInsights`) into three summary cards — cohort mastery, open-alert
 * severity counts, and review-queue depth — plus a reviewable-signals list
 * (`useCourseSignals`) whose rows open the T077 `SignalDetailDrawer`. F6 appends
 * the effectiveness tracker. A genuinely evidence-free course (`has_evidence
 * === false`) renders the designed empty state instead of fabricated zeros.
 */

interface CourseInsightsViewProps {
  readonly courseId: string;
}

export function CourseInsightsView({ courseId }: CourseInsightsViewProps) {
  const t = useTranslations("teacher.insights");
  const { data, isLoading, isError } = useCourseInsights(courseId);
  const [openSignalId, setOpenSignalId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("loadErrorTitle")}
        reason={t("loadErrorReason")}
      />
    );
  }

  if (!data.has_evidence) {
    return (
      <EmptyState
        variant="waiting"
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  const { cohort_mastery, alerts, review_queue } = data;

  return (
    <div className="space-y-6">
      <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("subtitle")}
      </p>

      <div className="grid gap-4 lg:grid-cols-3">
        <InsightCard
          title={t("mastery.title")}
          subtitle={t("mastery.subtitle")}
          icon={GraduationCap}
        >
          <div className="grid grid-cols-2 gap-3">
            <StatTile
              label={t("mastery.conceptsCovered")}
              value={t("mastery.conceptsCoveredValue", {
                withEvidence: cohort_mastery.concepts_with_evidence,
                total: cohort_mastery.concept_count,
              })}
            />
            <StatTile
              label={t("mastery.weakSignals")}
              value={cohort_mastery.weak_student_signals}
              tone={cohort_mastery.weak_student_signals > 0 ? "warning" : "default"}
            />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[12px]">
              <span className="text-[var(--color-text-muted)]">
                {t("mastery.avgMastery")}
              </span>
              <span className="font-semibold text-[var(--color-text)]">
                {cohort_mastery.avg_mastery === null
                  ? t("mastery.noAvg")
                  : formatFraction(cohort_mastery.avg_mastery)}
              </span>
            </div>
            <ProgressBar
              width={barWidth(cohort_mastery.avg_mastery)}
              tone="primary"
              label={t("mastery.avgMastery")}
            />
          </div>
        </InsightCard>

        <InsightCard
          title={t("alerts.title")}
          subtitle={t("alerts.subtitle")}
          icon={AlertTriangle}
        >
          {alerts.total === 0 ? (
            <p className="text-[13px] text-[var(--color-text-muted)]">
              {t("alerts.none")}
            </p>
          ) : (
            <div className="space-y-2.5">
              <SeverityRow
                label={t("alerts.critical")}
                count={alerts.critical}
                tone="critical"
              />
              <SeverityRow
                label={t("alerts.warning")}
                count={alerts.warning}
                tone="warning"
              />
              <SeverityRow
                label={t("alerts.info")}
                count={alerts.info}
                tone="info"
              />
              <p className="pt-1 text-[11px] text-[var(--color-text-muted)]">
                {t("alerts.total", { count: alerts.total })}
              </p>
            </div>
          )}
        </InsightCard>

        <InsightCard
          title={t("reviewQueue.title")}
          subtitle={t("reviewQueue.subtitle")}
          icon={Inbox}
        >
          {review_queue.total === 0 ? (
            <p className="text-[13px] text-[var(--color-text-muted)]">
              {t("reviewQueue.clear")}
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <StatTile
                label={t("reviewQueue.openAlerts")}
                value={review_queue.open_alerts}
              />
              <StatTile
                label={t("reviewQueue.pendingNotes")}
                value={review_queue.pending_notes}
              />
            </div>
          )}
        </InsightCard>
      </div>

      <SignalsPanel courseId={courseId} onOpen={setOpenSignalId} />

      <EffectivenessTracker courseId={courseId} />

      <SignalDetailDrawer
        signalId={openSignalId}
        onClose={() => setOpenSignalId(null)}
      />
    </div>
  );
}

interface SeverityRowProps {
  readonly label: string;
  readonly count: number;
  readonly tone: "critical" | "warning" | "info";
}

function SeverityRow({ label, count, tone }: SeverityRowProps) {
  const dot =
    tone === "critical"
      ? "bg-[var(--color-error)]"
      : tone === "warning"
        ? "bg-[var(--color-warning)]"
        : "bg-[var(--color-accent)]";
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2 text-[13px] text-[var(--color-text-secondary)]">
        <span className={cn("size-2 rounded-full", dot)} aria-hidden="true" />
        {label}
      </span>
      <span className="text-[15px] font-semibold text-[var(--color-text)]">
        {count}
      </span>
    </div>
  );
}

interface SignalsPanelProps {
  readonly courseId: string;
  readonly onOpen: (signalId: string) => void;
}

function SignalsPanel({ courseId, onOpen }: SignalsPanelProps) {
  const t = useTranslations("teacher.insights");
  const { data: signals, isLoading, isError } = useCourseSignals(courseId);

  return (
    <InsightCard title={t("signals.title")} icon={Users}>
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : isError ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("signals.loadError")}
        </p>
      ) : !signals || signals.length === 0 ? (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("signals.empty")}
        </p>
      ) : (
        <ul className="space-y-2">
          {signals.map((signal) => (
            <li key={signal.id}>
              <SignalRow signal={signal} onOpen={onOpen} />
            </li>
          ))}
        </ul>
      )}
    </InsightCard>
  );
}

interface SignalRowProps {
  readonly signal: TeacherSignal;
  readonly onOpen: (signalId: string) => void;
}

function SignalRow({ signal, onOpen }: SignalRowProps) {
  const t = useTranslations("teacher.insights");
  const pending = isPendingReview(signal.review_status);
  const statusLabel = t.has(`signals.status.${signal.review_status}`)
    ? t(`signals.status.${signal.review_status}`)
    : signal.review_status;

  return (
    <button
      type="button"
      onClick={() => onOpen(signal.id)}
      className="group flex w-full items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3 text-left transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-primary)]/40 hover:bg-[var(--color-surface-hover)]"
    >
      <div className="min-w-0 flex-1 space-y-1">
        <p className="truncate text-[13px] font-medium text-[var(--color-text)]">
          {signal.observed_signal}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
            {signal.user_id === null
              ? t("signals.cohort")
              : t("signals.student")}
          </span>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              reviewStatusToneClass(signal.review_status)
            )}
          >
            {pending ? `${statusLabel} · ${t("signals.needsReview")}` : statusLabel}
          </span>
        </div>
      </div>
      <ChevronRight
        aria-hidden="true"
        className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5"
      />
    </button>
  );
}
