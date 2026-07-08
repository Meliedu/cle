"use client";

import { useTranslations } from "next-intl";
import { Check, X } from "lucide-react";

import { StateBanner } from "@/components/patterns";
import { cn } from "@/lib/utils";
import type { ReportResponse } from "@/hooks/use-reports";

import { sendGateState } from "./report-format";

interface ReportSendGateProps {
  readonly report: ReportResponse;
}

/**
 * T083 gate surface — the designed `REPORT_NOT_REVIEWED` block (Decision 3).
 * A report cannot be sent or exported until it is `reviewed` AND carries at
 * least one evidence ref; until then this renders a `StateBanner tone="blocked"`
 * with a two-item checklist (reviewed? / evidence attached?) so the teacher sees
 * exactly what is outstanding. Renders nothing once the gate is satisfied — the
 * send/export buttons take over. Never rendered for an already-`sent` report.
 */
export function ReportSendGate({ report }: ReportSendGateProps) {
  const t = useTranslations("teacher.reports.gate");
  const gate = sendGateState(report);

  if (gate.met || report.status === "sent" || report.status === "archived") {
    return null;
  }

  return (
    <StateBanner
      tone="blocked"
      title={t("title")}
      reason={t("reason")}
      action={
        <ul className="space-y-1" aria-label={t("checklistLabel")}>
          <GateItem met={gate.reviewed} label={t("needsReview")} />
          <GateItem met={gate.hasEvidence} label={t("needsEvidence")} />
        </ul>
      }
    />
  );
}

function GateItem({
  met,
  label,
}: {
  readonly met: boolean;
  readonly label: string;
}) {
  const Icon = met ? Check : X;
  return (
    <li
      data-met={met}
      className={cn(
        "flex items-center gap-1.5 text-[12px]",
        met
          ? "text-[var(--color-success)]"
          : "text-[var(--color-text-secondary)]"
      )}
    >
      <Icon aria-hidden="true" strokeWidth={2.25} className="size-3.5 shrink-0" />
      {label}
    </li>
  );
}
