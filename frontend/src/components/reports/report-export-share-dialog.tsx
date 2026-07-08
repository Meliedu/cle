"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Download, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useExportReport,
  useReportShareSettings,
  type ReportExport,
  type ReportResponse,
  type ReportShareSettings,
} from "@/hooks/use-reports";

import { EvidenceAppendix } from "./evidence-appendix";
import { formatPeriodRange } from "./report-format";

interface ReportExportShareDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly courseId: string;
  readonly report: ReportResponse;
}

/** Trigger a client-side download of the export payload as JSON. */
function downloadExport(payload: ReportExport): void {
  if (typeof window === "undefined") return;
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `report-${payload.report.period}-${payload.report.id}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * T085 (+ T084) — export & share settings. Opening the dialog runs the audited
 * `POST /reports/{id}/export` (`useExportReport`), which returns the report, the
 * resolved evidence appendix, and the persisted share settings. The teacher
 * toggles the three share flags (each `PATCH`ed via `useReportShareSettings`),
 * previews the evidence appendix, and downloads the export. Only reachable once
 * the send gate is satisfied — the trigger button is disabled otherwise.
 */
export function ReportExportShareDialog({
  open,
  onOpenChange,
  courseId,
  report,
}: ReportExportShareDialogProps) {
  const t = useTranslations("teacher.reports.share");
  const exportReport = useExportReport(courseId);
  const shareSettings = useReportShareSettings(courseId);

  const [payload, setPayload] = useState<ReportExport | null>(null);
  const [flags, setFlags] = useState<ReportShareSettings | null>(null);

  const { mutateAsync: runExport } = exportReport;

  // Fetch the export payload once per open (the export is intentionally audited
  // server-side, so we don't re-run it on every render).
  useEffect(() => {
    if (!open) {
      setPayload(null);
      setFlags(null);
      return;
    }
    let cancelled = false;
    void runExport(report.id)
      .then((result) => {
        if (cancelled) return;
        setPayload(result);
        setFlags(result.share_settings);
      })
      .catch(() => {
        // Surfaced via exportReport.isError below.
      });
    return () => {
      cancelled = true;
    };
  }, [open, report.id, runExport]);

  const toggle = useCallback(
    (key: keyof ReportShareSettings, next: boolean) => {
      setFlags((prev) => (prev ? { ...prev, [key]: next } : prev));
      shareSettings.mutate({ reportId: report.id, [key]: next });
    },
    [shareSettings, report.id]
  );

  const loading = exportReport.isPending && !payload;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>
            {t("subtitle", {
              range: formatPeriodRange(report.period_start, report.period_end),
            })}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="space-y-3" aria-busy="true">
            <Skeleton className="h-10 w-full rounded-[var(--radius-md)]" />
            <Skeleton className="h-10 w-full rounded-[var(--radius-md)]" />
            <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />
          </div>
        ) : exportReport.isError || !payload || !flags ? (
          <StateBanner
            tone="warning"
            title={t("errorTitle")}
            reason={t("errorReason")}
          />
        ) : (
          <div className="max-h-[60vh] space-y-5 overflow-y-auto pr-1">
            <fieldset className="space-y-3">
              <legend className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                {t("settingsLegend")}
              </legend>
              <ToggleRow
                id="share-visible-to-student"
                label={t("visibleToStudent")}
                hint={t("visibleToStudentHint")}
                checked={flags.visible_to_student}
                onCheckedChange={(v) => toggle("visible_to_student", v)}
              />
              <ToggleRow
                id="share-allow-download"
                label={t("allowDownload")}
                hint={t("allowDownloadHint")}
                checked={flags.allow_download}
                onCheckedChange={(v) => toggle("allow_download", v)}
              />
              <ToggleRow
                id="share-include-appendix"
                label={t("includeAppendix")}
                hint={t("includeAppendixHint")}
                checked={flags.include_evidence_appendix}
                onCheckedChange={(v) =>
                  toggle("include_evidence_appendix", v)
                }
              />
            </fieldset>

            {flags.include_evidence_appendix ? (
              <section className="space-y-2.5">
                <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t("appendixTitle")}
                </h3>
                <EvidenceAppendix entries={payload.evidence_appendix} />
              </section>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("close")}
          </Button>
          <Button
            type="button"
            disabled={!payload || !flags?.allow_download}
            onClick={() => payload && downloadExport(payload)}
          >
            {exportReport.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Download aria-hidden="true" />
            )}
            {t("download")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface ToggleRowProps {
  readonly id: string;
  readonly label: string;
  readonly hint: string;
  readonly checked: boolean;
  readonly onCheckedChange: (checked: boolean) => void;
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onCheckedChange,
}: ToggleRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
      <div className="min-w-0 space-y-0.5">
        <label
          htmlFor={id}
          className="block text-[13px] font-medium text-[var(--color-text)]"
        >
          {label}
        </label>
        <p className="text-[12px] leading-snug text-[var(--color-text-secondary)]">
          {hint}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        aria-label={label}
      />
    </div>
  );
}
