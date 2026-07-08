"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Send, Share2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import {
  useApproveReport,
  useSendReport,
  type ReportResponse,
} from "@/hooks/use-reports";

import { ReportConfirmDialog } from "./report-confirm-dialog";
import { ReportExportShareDialog } from "./report-export-share-dialog";
import { ReportSendGate } from "./report-send-gate";
import { canSendReport } from "./report-format";
import { formatReportDate } from "./report-format";

interface ReportActionsProps {
  readonly courseId: string;
  readonly report: ReportResponse;
}

/**
 * T083 action bar for a report detail — the state-machine transitions layered
 * above the body sections. `draft` offers Approve (→ `reviewed`); `reviewed`
 * offers Send (→ `sent`) and Export & share, both gated behind
 * `canSendReport` (Decision 3) with the `ReportSendGate` banner explaining any
 * shortfall; `sent`/`archived` show a terminal status banner. Approve/send run
 * behind a confirm dialog that surfaces the typed 409s as blocked banners.
 */
export function ReportActions({ courseId, report }: ReportActionsProps) {
  const t = useTranslations("teacher.reports.actions");
  const tGate = useTranslations("teacher.reports.gate");
  const approve = useApproveReport(courseId);
  const send = useSendReport(courseId);

  const [approveOpen, setApproveOpen] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);

  const sendable = canSendReport(report);

  const approveBlockedReason = useCallback(
    (code: string | undefined): string | null =>
      code === "REPORT_INVALID_TRANSITION" ? t("approveInvalidReason") : null,
    [t]
  );
  const sendBlockedReason = useCallback(
    (code: string | undefined): string | null =>
      code === "REPORT_NOT_REVIEWED" ? tGate("reason") : null,
    [tGate]
  );

  if (report.status === "sent") {
    return (
      <StateBanner
        tone="success"
        title={t("sentTitle")}
        reason={
          report.sent_at
            ? t("sentReason", { date: formatReportDate(report.sent_at) })
            : t("sentReasonNoDate")
        }
      />
    );
  }

  if (report.status === "archived") {
    return (
      <StateBanner
        tone="info"
        title={t("archivedTitle")}
        reason={t("archivedReason")}
      />
    );
  }

  return (
    <div className="space-y-4">
      <ReportSendGate report={report} />

      <div className="flex flex-wrap items-center gap-2.5">
        {report.status === "draft" ? (
          <Button
            type="button"
            size="lg"
            onClick={() => setApproveOpen(true)}
          >
            <CheckCircle2 aria-hidden="true" />
            {t("approve")}
          </Button>
        ) : null}

        {report.status === "reviewed" ? (
          <>
            <Button
              type="button"
              size="lg"
              disabled={!sendable}
              onClick={() => setSendOpen(true)}
            >
              <Send aria-hidden="true" />
              {t("send")}
            </Button>
            <Button
              type="button"
              size="lg"
              variant="outline"
              disabled={!sendable}
              onClick={() => setShareOpen(true)}
            >
              <Share2 aria-hidden="true" />
              {t("exportShare")}
            </Button>
          </>
        ) : null}
      </div>

      <ReportConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title={t("approveConfirmTitle")}
        body={t("approveConfirmBody")}
        confirmLabel={t("approveConfirm")}
        cancelLabel={t("cancel")}
        pendingLabel={t("approving")}
        genericErrorLabel={t("genericError")}
        isPending={approve.isPending}
        onConfirm={async () => {
          await approve.mutateAsync(report.id);
        }}
        blockedReasonFor={approveBlockedReason}
      />

      <ReportConfirmDialog
        open={sendOpen}
        onOpenChange={setSendOpen}
        title={t("sendConfirmTitle")}
        body={t("sendConfirmBody")}
        confirmLabel={t("sendConfirm")}
        cancelLabel={t("cancel")}
        pendingLabel={t("sending")}
        genericErrorLabel={t("genericError")}
        isPending={send.isPending}
        onConfirm={async () => {
          await send.mutateAsync(report.id);
        }}
        blockedReasonFor={sendBlockedReason}
      />

      <ReportExportShareDialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        courseId={courseId}
        report={report}
      />
    </div>
  );
}
