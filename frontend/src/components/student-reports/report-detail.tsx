"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { EmptyState, PageHeader, StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { useMyReport } from "@/hooks/use-reports";
import { usePilotConfig } from "@/hooks/use-pilot-config";

import { ClaimLimitsNote } from "./claim-limits-note";
import { ReportBodySections } from "./report-body-sections";
import { ReportDeliveryState } from "./report-delivery-state";
import { formatPeriodRange, REPORT_PERIOD_META } from "./report-meta";

/**
 * S067 weekly / S068 end-term report detail. Renders the typed `body` sections
 * a student was SENT (draft/reviewed rows never reach the student read), the
 * S069 delivery state, and the claim-limits disclaimer verbatim — preferring
 * the report's own `body.claim_limits` snapshot, falling back to the live pilot
 * config. Weekly and end-term share this component; the period only changes the
 * header copy and which body sections are populated.
 */
interface ReportDetailProps {
  readonly courseId: string;
  readonly reportId: string;
}

export function ReportDetail({ courseId, reportId }: ReportDetailProps) {
  const t = useTranslations("student.reports");
  const { data: report, isLoading, isError } = useMyReport(reportId);
  const { config } = usePilotConfig();
  const backHref = `/student/courses/${courseId}/reports`;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="h-20 w-full rounded-[var(--radius-xl)]" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (isError || !report) {
    return (
      <div className="space-y-4">
        <BackLink href={backHref} label={t("detail.back")} />
        <StateBanner
          tone="warning"
          title={t("detail.error.title")}
          reason={t("detail.error.reason")}
        />
      </div>
    );
  }

  const meta = REPORT_PERIOD_META[report.period];
  const range = formatPeriodRange(report.period_start, report.period_end);
  const pilotFallback = config?.claim_limits?.report ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={t(`period.${meta.key}`)}
        description={range ?? undefined}
        breadcrumb={
          <Link href={backHref} className="hover:text-[var(--color-text)]">
            {t("detail.back")}
          </Link>
        }
      />

      <ReportDeliveryState report={report} />

      {report.body ? (
        <>
          <ReportBodySections body={report.body} />
          <ClaimLimitsNote
            text={report.body.claim_limits}
            fallback={pilotFallback}
          />
        </>
      ) : (
        // A sent report should always carry a body; degrade honestly if not.
        <EmptyState
          variant="waiting"
          title={t("detail.pending.title")}
          reason={t("detail.pending.reason")}
        />
      )}
    </div>
  );
}

function BackLink({ href, label }: { readonly href: string; readonly label: string }) {
  return (
    <Link
      href={href}
      className="inline-flex text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
    >
      {label}
    </Link>
  );
}
