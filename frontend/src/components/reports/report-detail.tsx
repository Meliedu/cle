"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowLeft,
  CheckSquare,
  ClipboardList,
  ListChecks,
  PencilLine,
  TrendingDown,
} from "lucide-react";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useReport,
  type ReportBody,
  type ReportResponse,
} from "@/hooks/use-reports";

import { ReportStatusChip } from "./report-status-chip";
import { ReportBodyEditor } from "./report-body-editor";
import {
  formatMasteryPercent,
  formatPeriodRange,
  isReportEditable,
} from "./report-format";

interface ReportDetailProps {
  readonly courseId: string;
  readonly reportId: string;
  /** Return to the archive list. */
  readonly onBack: () => void;
}

/**
 * T081 — one report's detail. Renders the typed `body` sections composed from
 * reviewed evidence (summary, at-a-glance completed work, observations, weak
 * points, next actions) plus the verbatim `claim_limits` disclaimer and the
 * evidence-ref list. Hosts the T082 draft editor (only a `draft` is editable).
 * F3 layers the approve / send / export / appendix / share surfaces on top.
 */
export function ReportDetail({ courseId, reportId, onBack }: ReportDetailProps) {
  const t = useTranslations("teacher.reports");
  const query = useReport(reportId);
  const [editing, setEditing] = useState(false);

  if (query.isLoading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="space-y-4">
        <BackLink label={t("detail.back")} onBack={onBack} />
        <StateBanner
          tone="warning"
          title={t("detail.loadErrorTitle")}
          reason={t("detail.loadErrorReason")}
        />
      </div>
    );
  }

  const report = query.data;
  const editable = isReportEditable(report.status);

  return (
    <div className="space-y-6">
      <PageHeader
        title={formatPeriodRange(report.period_start, report.period_end)}
        description={t(`detail.periodKind.${report.period}`)}
        breadcrumb={<BackLink label={t("detail.back")} onBack={onBack} />}
        actions={
          <div className="flex items-center gap-3">
            <ReportStatusChip
              status={report.status}
              label={t(`status.${report.status}`)}
            />
            {!editing ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={!editable}
                title={!editable ? t("detail.editDisabledReason") : undefined}
                onClick={() => setEditing(true)}
              >
                <PencilLine aria-hidden="true" />
                {t("detail.edit")}
              </Button>
            ) : null}
          </div>
        }
      />

      {editing ? (
        <ReportBodyEditor
          courseId={courseId}
          report={report}
          onDone={() => setEditing(false)}
        />
      ) : (
        <ReportBodySections report={report} />
      )}
    </div>
  );
}

/** All read-only body sections, extracted so the editor can swap in cleanly. */
export function ReportBodySections({
  report,
}: {
  readonly report: ReportResponse;
}) {
  const t = useTranslations("teacher.reports.detail");
  const body = report.body;

  if (!body) {
    return (
      <StateBanner
        tone="waiting"
        title={t("noBodyTitle")}
        reason={t("noBodyReason")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <Section
        icon={ClipboardList}
        title={t("sections.summary")}
      >
        <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          {body.summary || t("empty.summary")}
        </p>
      </Section>

      <Section icon={CheckSquare} title={t("sections.completedWork")}>
        <p className="text-[14px] text-[var(--color-text-secondary)]">
          {t("completedCount", { count: body.completed_work.completed_count })}
        </p>
      </Section>

      <Section icon={ListChecks} title={t("sections.observations")}>
        <BulletList
          items={body.observations}
          emptyLabel={t("empty.observations")}
        />
      </Section>

      <Section icon={TrendingDown} title={t("sections.weakPoints")}>
        {body.weak_points.length === 0 ? (
          <p className="text-[13px] text-[var(--color-text-muted)]">
            {t("empty.weakPoints")}
          </p>
        ) : (
          <ul className="space-y-2">
            {body.weak_points.map((wp) => (
              <li
                key={wp.concept_id}
                className="flex items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5"
              >
                <span className="min-w-0 truncate text-[13px] text-[var(--color-text)]">
                  {wp.name}
                </span>
                <span className="shrink-0 text-[13px] font-semibold tabular-nums text-[var(--color-warning)]">
                  {formatMasteryPercent(wp.mastery_score)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section icon={ListChecks} title={t("sections.nextActions")}>
        <BulletList
          items={body.next_actions}
          emptyLabel={t("empty.nextActions")}
        />
      </Section>

      <EvidenceRefList report={report} />

      {body.claim_limits ? (
        <StateBanner
          tone="info"
          title={t("sections.claimLimits")}
          reason={body.claim_limits}
        />
      ) : null}
    </div>
  );
}

function EvidenceRefList({ report }: { readonly report: ReportResponse }) {
  const t = useTranslations("teacher.reports.detail");
  return (
    <Section icon={ClipboardList} title={t("sections.evidence")}>
      <p className="text-[13px] text-[var(--color-text-secondary)]">
        {t("evidenceCount", { count: report.evidence_refs.length })}
      </p>
    </Section>
  );
}

interface SectionProps {
  readonly icon: typeof ClipboardList;
  readonly title: string;
  readonly children: React.ReactNode;
}

function Section({ icon: Icon, title, children }: SectionProps) {
  return (
    <section className="space-y-2.5 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <h3 className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
        {title}
      </h3>
      {children}
    </section>
  );
}

function BulletList({
  items,
  emptyLabel,
}: {
  readonly items: readonly string[];
  readonly emptyLabel: string;
}) {
  if (items.length === 0) {
    return (
      <p className="text-[13px] text-[var(--color-text-muted)]">{emptyLabel}</p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li
          key={i}
          className="flex gap-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]"
        >
          <span
            aria-hidden="true"
            className="mt-2 size-1.5 shrink-0 rounded-full bg-[var(--color-primary)]"
          />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

function BackLink({
  label,
  onBack,
}: {
  readonly label: string;
  readonly onBack: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="inline-flex items-center gap-1 text-[13px] text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
    >
      <ArrowLeft aria-hidden="true" className="size-3.5" />
      {label}
    </button>
  );
}
