"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Save, X } from "lucide-react";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api";
import {
  useUpdateReport,
  type ReportBody,
  type ReportResponse,
} from "@/hooks/use-reports";

import { isReportEditable } from "./report-format";

interface ReportBodyEditorProps {
  readonly courseId: string;
  readonly report: ReportResponse;
  /** Close the editor (on save success or cancel). */
  readonly onDone: () => void;
}

/** Split a newline-separated textarea into a trimmed, non-empty item list. */
function toLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/**
 * T082 — draft report body editor. Edits the narrative sections a teacher owns
 * (summary, observations, next actions) plus the completed-work count, then
 * `PATCH`es the full `body` via `useUpdateReport`. The evidence-derived sections
 * (weak points, claim limits) pass through unchanged — they are composed from
 * reviewed evidence, not free text. Only a `draft` is editable; a backend
 * `REPORT_NOT_EDITABLE` 409 (e.g. the report was approved in another tab) is
 * surfaced as a `StateBanner tone="blocked"`.
 */
export function ReportBodyEditor({
  courseId,
  report,
  onDone,
}: ReportBodyEditorProps) {
  const t = useTranslations("teacher.reports.edit");
  const update = useUpdateReport(courseId);
  const body = report.body;

  const [summary, setSummary] = useState(body?.summary ?? "");
  const [observations, setObservations] = useState(
    (body?.observations ?? []).join("\n")
  );
  const [nextActions, setNextActions] = useState(
    (body?.next_actions ?? []).join("\n")
  );
  const [completedCount, setCompletedCount] = useState(
    String(body?.completed_work.completed_count ?? 0)
  );
  const [blockedReason, setBlockedReason] = useState<string | null>(null);
  const [genericError, setGenericError] = useState(false);

  const editable = isReportEditable(report.status);

  const submit = useCallback(async () => {
    if (!body) return;
    setBlockedReason(null);
    setGenericError(false);

    const parsedCount = Number.parseInt(completedCount, 10);
    const nextBody: ReportBody = {
      ...body,
      summary: summary.trim(),
      observations: toLines(observations),
      next_actions: toLines(nextActions),
      completed_work: {
        completed_count: Number.isFinite(parsedCount)
          ? Math.max(0, parsedCount)
          : body.completed_work.completed_count,
      },
    };

    try {
      await update.mutateAsync({ reportId: report.id, body: nextBody });
      onDone();
    } catch (error) {
      if (error instanceof ApiError && error.code === "REPORT_NOT_EDITABLE") {
        setBlockedReason(error.detail ?? t("notEditableReason"));
      } else {
        setGenericError(true);
      }
    }
  }, [
    body,
    completedCount,
    summary,
    observations,
    nextActions,
    update,
    report.id,
    onDone,
    t,
  ]);

  if (!body) return null;

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="space-y-1.5">
        <h3 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h3>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {!editable ? (
        <StateBanner
          tone="blocked"
          title={t("notEditableTitle")}
          reason={t("notEditableReason")}
        />
      ) : null}

      <Field id="report-summary" label={t("summaryLabel")}>
        <Textarea
          id="report-summary"
          value={summary}
          disabled={!editable}
          onChange={(e) => setSummary(e.target.value)}
          className="min-h-20"
        />
      </Field>

      <Field
        id="report-observations"
        label={t("observationsLabel")}
        hint={t("observationsHint")}
      >
        <Textarea
          id="report-observations"
          value={observations}
          disabled={!editable}
          onChange={(e) => setObservations(e.target.value)}
          className="min-h-24"
        />
      </Field>

      <Field
        id="report-next-actions"
        label={t("nextActionsLabel")}
        hint={t("nextActionsHint")}
      >
        <Textarea
          id="report-next-actions"
          value={nextActions}
          disabled={!editable}
          onChange={(e) => setNextActions(e.target.value)}
          className="min-h-24"
        />
      </Field>

      <Field id="report-completed-count" label={t("completedCountLabel")}>
        <input
          id="report-completed-count"
          type="number"
          min={0}
          inputMode="numeric"
          value={completedCount}
          disabled={!editable}
          onChange={(e) => setCompletedCount(e.target.value)}
          className="h-9 w-32 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40 disabled:cursor-not-allowed disabled:opacity-60"
        />
      </Field>

      {blockedReason ? (
        <StateBanner
          tone="blocked"
          title={t("notEditableTitle")}
          reason={blockedReason}
        />
      ) : null}
      {genericError ? (
        <p role="alert" className="text-[13px] text-[var(--color-error)]">
          {t("genericError")}
        </p>
      ) : null}

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          size="lg"
          disabled={!editable || update.isPending}
        >
          {update.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <Save aria-hidden="true" />
          )}
          {update.isPending ? t("saving") : t("save")}
        </Button>
        <Button type="button" size="lg" variant="outline" onClick={onDone}>
          <X aria-hidden="true" />
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}

interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly hint?: string;
  readonly children: React.ReactNode;
}

function Field({ id, label, hint, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
      >
        {label}
      </label>
      {children}
      {hint ? (
        <p className="text-[11px] leading-snug text-[var(--color-text-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
