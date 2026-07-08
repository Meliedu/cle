"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { EmptyState, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useMyReports,
  type ReportPeriod,
  type ReportResponse,
} from "@/hooks/use-reports";

import { formatPeriodRange, formatReportDate, REPORT_PERIOD_META } from "./report-meta";

/**
 * S066 — student report archive. Lists the caller's SENT reports only (the hook
 * never returns draft/reviewed rows), newest first, with a period filter. When
 * the instructor has sent nothing yet the archive collapses to a designed
 * waiting shell (the S069 "not yet sent" state) — never a blank div and never
 * fabricated draft content.
 */
interface ReportArchiveProps {
  readonly courseId: string;
}

type PeriodFilter = "all" | ReportPeriod;

const FILTERS: readonly PeriodFilter[] = ["all", "weekly", "end_term"];

export function ReportArchive({ courseId }: ReportArchiveProps) {
  const t = useTranslations("student.reports");
  const { data, isLoading, isError } = useMyReports(courseId);
  const [filter, setFilter] = useState<PeriodFilter>("all");

  const sorted = useMemo(() => {
    const rows = data ? [...data] : [];
    return rows.sort(
      (a, b) => new Date(b.period_end).getTime() - new Date(a.period_end).getTime()
    );
  }, [data]);

  const visible = useMemo(
    () => (filter === "all" ? sorted : sorted.filter((r) => r.period === filter)),
    [sorted, filter]
  );

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px] w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  // No sent reports at all → the honest "not yet sent" waiting shell (S069).
  if (sorted.length === 0) {
    return (
      <EmptyState
        variant="waiting"
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  return (
    <section className="space-y-4">
      <div
        role="tablist"
        aria-label={t("filter.label")}
        className="flex flex-wrap gap-1.5"
      >
        {FILTERS.map((value) => {
          const isActive = value === filter;
          return (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setFilter(value)}
              className={cn(
                "min-h-9 rounded-[var(--radius-pill)] border px-3.5 text-[13px] font-medium transition-colors duration-[var(--duration-fast)]",
                isActive
                  ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-text)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)]"
              )}
            >
              {t(`filter.${value}`)}
            </button>
          );
        })}
      </div>

      {visible.length === 0 ? (
        <EmptyState
          variant="empty"
          title={t("filterEmpty.title")}
          reason={t("filterEmpty.reason")}
        />
      ) : (
        <ul className="space-y-2">
          {visible.map((report) => (
            <ReportRow key={report.id} report={report} courseId={courseId} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** One archive row: period icon, title, coverage/sent meta, delivery chip. */
function ReportRow({
  report,
  courseId,
}: {
  readonly report: ReportResponse;
  readonly courseId: string;
}) {
  const t = useTranslations("student.reports");
  const meta = REPORT_PERIOD_META[report.period];
  const Icon = meta.icon;
  const range = formatPeriodRange(report.period_start, report.period_end);
  const sentOn = formatReportDate(report.sent_at);

  return (
    <li>
      <Link
        href={`/student/courses/${courseId}/reports/${report.id}`}
        className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
      >
        <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-cream)] text-[var(--color-primary-hover)]">
          <Icon aria-hidden="true" className="size-5" />
        </span>

        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="truncate text-[14px] font-semibold text-[var(--color-text)]">
            {t(`period.${meta.key}`)}
          </p>
          <p className="truncate text-[12px] text-[var(--color-text-muted)]">
            {range ?? t(`type.${meta.key}`)}
          </p>
        </div>

        <span className="hidden shrink-0 items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] px-2.5 py-1 text-[11px] font-semibold text-[var(--color-success)] sm:inline-flex">
          {sentOn ? t("chip.sentOn", { date: sentOn }) : t("chip.sent")}
        </span>

        <ChevronRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--color-text-muted)]"
        />
      </Link>
    </li>
  );
}
