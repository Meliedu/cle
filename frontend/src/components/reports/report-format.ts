import type { ReportResponse, ReportStatus } from "@/hooks/use-reports";

/**
 * Presentation helpers shared by the report archive / detail / action surfaces.
 * Pure + locale-stable ("en-GB" day-month-year, matching the Figma date style
 * "16 - 22 Jun 2026") so they are trivially unit-testable and never leak a
 * hardcoded user string.
 */

const DAY_MONTH_YEAR = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const DAY_MONTH = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
});

/** En-dash range separator, padded with plain ASCII spaces. */
const DASH = "–";

function parse(iso: string): Date | null {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Collapse the non-breaking / narrow / thin spaces some ICU builds emit inside
 * formatted dates down to plain spaces, so output is deterministic across
 * environments (and unit-testable against literal strings).
 */
function normalizeSpaces(value: string): string {
  return value.replace(/[   ]/g, " ");
}

/** Full "25 Jun 2026" date, or the raw input when unparseable. */
export function formatReportDate(iso: string): string {
  const d = parse(iso);
  return d ? normalizeSpaces(DAY_MONTH_YEAR.format(d)) : iso;
}

/**
 * Compact period range for a report row, e.g. "16 - 22 Jun 2026". Collapses the
 * shared month/year onto the end date; falls back gracefully on bad input.
 */
export function formatPeriodRange(start: string, end: string): string {
  const s = parse(start);
  const e = parse(end);
  if (!s || !e) return normalizeSpaces(`${start} ${DASH} ${end}`);

  const sameMonth =
    s.getUTCFullYear() === e.getUTCFullYear() &&
    s.getUTCMonth() === e.getUTCMonth();
  const sameYear = s.getUTCFullYear() === e.getUTCFullYear();

  const left = sameMonth
    ? String(s.getUTCDate())
    : sameYear
      ? DAY_MONTH.format(s)
      : DAY_MONTH_YEAR.format(s);

  return normalizeSpaces(`${left} ${DASH} ${DAY_MONTH_YEAR.format(e)}`);
}

/** Mastery score (0-1) rendered as a whole-percent string, e.g. "42%". */
export function formatMasteryPercent(score: number): string {
  const clamped = Math.max(0, Math.min(1, score));
  return `${Math.round(clamped * 100)}%`;
}

/**
 * The send/export gate (Decision 3, backend `REPORT_NOT_REVIEWED`): a report
 * may only be sent or exported once it is `reviewed` AND carries at least one
 * evidence ref. Mirrored client-side so the buttons disable *before* a doomed
 * request and the blocked banner can explain exactly what is missing.
 */
export function canSendReport(report: ReportResponse): boolean {
  return report.status === "reviewed" && report.evidence_refs.length > 0;
}

/** A draft is the only editable state (backend `REPORT_NOT_EDITABLE`). */
export function isReportEditable(status: ReportStatus): boolean {
  return status === "draft";
}

/** Which gate requirements a report has yet to satisfy, for the checklist. */
export interface SendGateState {
  readonly reviewed: boolean;
  readonly hasEvidence: boolean;
  readonly met: boolean;
}

export function sendGateState(report: ReportResponse): SendGateState {
  const reviewed =
    report.status === "reviewed" ||
    report.status === "sent" ||
    report.status === "archived";
  const hasEvidence = report.evidence_refs.length > 0;
  return { reviewed, hasEvidence, met: canSendReport(report) };
}
