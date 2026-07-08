"use client";

import { CheckCircle2, Mail, ShieldCheck, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import type { ReportResponse } from "@/hooks/use-reports";

import { formatReportDateTime } from "./report-meta";

/**
 * S069 — report delivery state. The student read only ever returns `sent`
 * reports (a not-yet-sent report is simply ABSENT — that "waiting" case is the
 * archive's empty shell, never draft content). So this surface reads as a
 * confirmed-delivery banner plus a short designed timeline. The timeline also
 * makes the Core §0.2 guarantee visible: a report was reviewed by the
 * instructor BEFORE it reached the student. If `sent_at` is somehow missing we
 * degrade to a calm waiting banner rather than inventing a delivery time.
 */
interface ReportDeliveryStateProps {
  readonly report: ReportResponse;
}

interface TimelineStep {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly detail: string | null;
}

export function ReportDeliveryState({ report }: ReportDeliveryStateProps) {
  const t = useTranslations("student.reports.delivery");
  const sentAt = formatReportDateTime(report.sent_at);
  const reviewedAt = formatReportDateTime(report.reviewed_at);

  if (report.status !== "sent" || !sentAt) {
    // Defensive: never present draft content as delivered.
    return (
      <StateBanner
        tone="waiting"
        title={t("pending.title")}
        reason={t("pending.reason")}
      />
    );
  }

  const steps: readonly TimelineStep[] = [
    ...(reviewedAt
      ? [
          {
            icon: ShieldCheck,
            title: t("steps.reviewed.title"),
            detail: t("steps.reviewed.detail", { at: reviewedAt }),
          },
        ]
      : []),
    {
      icon: Mail,
      title: t("steps.sent.title"),
      detail: t("steps.sent.detail", { at: sentAt }),
    },
  ];

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-success)]/40 bg-[var(--color-success-light)] p-4">
      <div className="flex items-start gap-3">
        <CheckCircle2
          aria-hidden="true"
          strokeWidth={1.85}
          className="mt-0.5 size-5 shrink-0 text-[var(--color-success)]"
        />
        <div className="min-w-0 space-y-0.5">
          <p className="text-[14px] font-semibold leading-snug tracking-tight text-[var(--color-text)]">
            {t("sent.title")}
          </p>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("sent.reason")}
          </p>
        </div>
      </div>

      <ol className="space-y-0 pl-1">
        {steps.map((step, i) => (
          <li key={i} className="relative flex gap-3 pb-4 last:pb-0">
            {/* Connector line between dots (hidden on the last step). */}
            {i < steps.length - 1 ? (
              <span
                aria-hidden="true"
                className="absolute left-[13px] top-7 bottom-0 w-px bg-[var(--color-success)]/30"
              />
            ) : null}
            <span className="relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border border-[var(--color-success)]/40 bg-[var(--color-surface)] text-[var(--color-success)]">
              <step.icon aria-hidden="true" className="size-3.5" />
            </span>
            <div className="min-w-0 pt-0.5">
              <p className="text-[13px] font-semibold text-[var(--color-text)]">
                {step.title}
              </p>
              {step.detail ? (
                <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
                  {step.detail}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
