import { CalendarDays, GraduationCap, type LucideIcon } from "lucide-react";

import type { ReportPeriod } from "@/hooks/use-reports";

/**
 * Presentation metadata for the two report periods. The student never edits a
 * report, so this is purely read-side: an icon + i18n key stem per period,
 * shared by the archive rows (S066) and the detail header (S067/S068). Labels
 * themselves live in `student.reports.*` next-intl keys — this map only carries
 * the icon and the key suffix so copy stays in one place.
 */
export interface ReportPeriodMeta {
  readonly icon: LucideIcon;
  /** i18n key suffix under `student.reports.period.*`. */
  readonly key: ReportPeriod;
}

export const REPORT_PERIOD_META: Record<ReportPeriod, ReportPeriodMeta> = {
  weekly: { icon: CalendarDays, key: "weekly" },
  end_term: { icon: GraduationCap, key: "end_term" },
};

const DATE_FMT = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const DATETIME_FMT = new Intl.DateTimeFormat("en-GB", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

/** Safely parse an ISO timestamp, returning `null` on an unparseable value. */
function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** `26 Jun 2026` — a calm absolute date for sent/coverage lines. */
export function formatReportDate(iso: string | null | undefined): string | null {
  const date = parse(iso);
  return date ? DATE_FMT.format(date) : null;
}

/** `26 Jun 2026, 10:15` — the delivery timestamp shown on the sent banner. */
export function formatReportDateTime(
  iso: string | null | undefined
): string | null {
  const date = parse(iso);
  return date ? DATETIME_FMT.format(date) : null;
}

/** `12 Jun – 26 Jun 2026` — the window a report covers, for the detail header. */
export function formatPeriodRange(
  startIso: string,
  endIso: string
): string | null {
  const start = parse(startIso);
  const end = parse(endIso);
  if (!start || !end) return null;
  return `${DATE_FMT.format(start)} – ${DATE_FMT.format(end)}`;
}
