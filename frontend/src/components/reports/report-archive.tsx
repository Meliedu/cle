"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronRight, FileText } from "lucide-react";

import { EmptyState, PageHeader, StateBanner } from "@/components/patterns";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useReports,
  type ReportPeriod,
  type ReportResponse,
  type ReportStatus,
} from "@/hooks/use-reports";

import { ReportStatusChip } from "./report-status-chip";
import { formatPeriodRange } from "./report-format";

interface ReportArchiveProps {
  readonly courseId: string;
  /** Open one report's detail view. */
  readonly onSelect: (reportId: string) => void;
}

type PeriodFilter = "all" | ReportPeriod;

const PERIOD_FILTERS: readonly PeriodFilter[] = ["all", "weekly", "end_term"];

/** Fixed status order so the archive groups always read the same top-to-bottom. */
const STATUS_ORDER: readonly ReportStatus[] = [
  "draft",
  "reviewed",
  "sent",
  "archived",
];

function groupByStatus(
  reports: readonly ReportResponse[]
): ReadonlyMap<ReportStatus, readonly ReportResponse[]> {
  const map = new Map<ReportStatus, ReportResponse[]>();
  for (const report of reports) {
    const list = map.get(report.status) ?? [];
    list.push(report);
    map.set(report.status, list);
  }
  return map;
}

/**
 * T080 — the teacher course report archive. Reports from `useReports` grouped
 * by `status` (one visual treatment each) under a `weekly` / `end_term` period
 * filter. Every row opens the T081 detail. Designed loading / error / empty
 * states — never a blank region (Figma T086 "no evidence yet").
 */
export function ReportArchive({ courseId, onSelect }: ReportArchiveProps) {
  const t = useTranslations("teacher.reports");
  const [period, setPeriod] = useState<PeriodFilter>("all");
  const query = useReports(
    courseId,
    period === "all" ? undefined : { period }
  );

  const grouped = useMemo(
    () => groupByStatus(query.data ?? []),
    [query.data]
  );
  const total = query.data?.length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        as="h2"
        title={t("archive.title")}
        description={t("archive.subtitle")}
      />

      <div
        role="group"
        aria-label={t("archive.filterLabel")}
        className="flex flex-wrap gap-2"
      >
        {PERIOD_FILTERS.map((f) => {
          const active = period === f;
          return (
            <button
              key={f}
              type="button"
              aria-pressed={active}
              onClick={() => setPeriod(f)}
              className={cn(
                "rounded-[var(--radius-pill)] border px-3 py-1.5 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]",
                active
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
              )}
            >
              {t(`archive.period.${f}`)}
            </button>
          );
        })}
      </div>

      {query.isLoading ? (
        <div className="space-y-3" aria-busy="true">
          <Skeleton className="h-20 w-full rounded-[var(--radius-lg)]" />
          <Skeleton className="h-20 w-full rounded-[var(--radius-lg)]" />
          <Skeleton className="h-20 w-full rounded-[var(--radius-lg)]" />
        </div>
      ) : query.isError ? (
        <StateBanner
          tone="warning"
          title={t("archive.loadErrorTitle")}
          reason={t("archive.loadErrorReason")}
        />
      ) : total === 0 ? (
        <EmptyState
          icon={FileText}
          title={t("archive.emptyTitle")}
          reason={t("archive.emptyReason")}
        />
      ) : (
        <div className="space-y-8">
          {STATUS_ORDER.map((status) => {
            const rows = grouped.get(status);
            if (!rows || rows.length === 0) return null;
            return (
              <section key={status} className="space-y-3">
                <div className="flex items-center gap-2">
                  <ReportStatusChip
                    status={status}
                    label={t(`status.${status}`)}
                  />
                  <span className="text-[12px] text-[var(--color-text-muted)]">
                    {t("archive.groupCount", { count: rows.length })}
                  </span>
                </div>

                <ul className="space-y-2.5">
                  {rows.map((report) => (
                    <li key={report.id}>
                      <ReportRow
                        report={report}
                        audienceLabel={t(`archive.audience.${report.audience}`)}
                        periodLabel={t(`archive.period.${report.period}`)}
                        evidenceLabel={t("archive.evidenceCount", {
                          count: report.evidence_refs.length,
                        })}
                        openLabel={t("archive.open")}
                        onSelect={() => onSelect(report.id)}
                      />
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

interface ReportRowProps {
  readonly report: ReportResponse;
  readonly audienceLabel: string;
  readonly periodLabel: string;
  readonly evidenceLabel: string;
  readonly openLabel: string;
  readonly onSelect: () => void;
}

function ReportRow({
  report,
  audienceLabel,
  periodLabel,
  evidenceLabel,
  openLabel,
  onSelect,
}: ReportRowProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-label={openLabel}
      className="group flex w-full items-center gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
    >
      <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)]">
        <FileText
          aria-hidden="true"
          strokeWidth={1.75}
          className="size-4 text-[var(--color-text-muted)]"
        />
      </span>

      <div className="min-w-0 flex-1 space-y-1">
        <p className="truncate text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
          {formatPeriodRange(report.period_start, report.period_end)}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-[var(--color-text-secondary)]">
          <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
            {periodLabel}
          </Badge>
          <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
            {audienceLabel}
          </Badge>
          <span>{evidenceLabel}</span>
        </div>
      </div>

      <ChevronRight
        aria-hidden="true"
        className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5"
      />
    </button>
  );
}
