"use client";

import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import { useRoster, type RosterEntry } from "@/hooks/use-enrollment";

interface RosterDetailProps {
  readonly courseId: string;
}

type Translate = ReturnType<typeof useTranslations>;

/** Known enrolment statuses map to a label; anything else shows verbatim. */
const KNOWN_STATUSES = new Set(["active", "pending", "rejected"]);

function statusLabel(t: Translate, status: string): string {
  return KNOWN_STATUSES.has(status) ? t(`status.${status}`) : status;
}

/** Locale date for an enrolment, e.g. "15 Jan 2026". */
function formatJoined(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Two-letter initials for the avatar chip, falling back to the email. */
function initials(entry: RosterEntry): string {
  const source = entry.full_name?.trim() || entry.email;
  const parts = source.split(/\s+/).filter(Boolean);
  const chars =
    parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : source.slice(0, 2);
  return chars.toUpperCase();
}

/**
 * T032 — read-only class roster detail. Lists the active students of a course
 * via `useRoster` (shared with the T029/T031 counts): name, email, joined
 * date, and enrolment status. Instructors are filtered out — this is the
 * student roster. Approving pending join requests is the T033 screen (Task
 * 15); this view only reads.
 */
export function RosterDetail({ courseId }: RosterDetailProps) {
  const t = useTranslations("teacher.enrollment.roster");
  const { data, isLoading } = useRoster(courseId);

  const students: readonly RosterEntry[] = data
    ? [...data]
        .filter((r) => r.role === "student")
        .sort((a, b) => a.enrolled_at.localeCompare(b.enrolled_at))
    : [];

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : students.length === 0 ? (
        <EmptyState title={t("empty.title")} reason={t("empty.reason")} />
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--color-border)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[12px] uppercase tracking-wide text-[var(--color-text-muted)]">
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.student")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.email")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.joined")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.status")}
                </th>
              </tr>
            </thead>
            <tbody>
              {students.map((entry) => (
                <tr
                  key={entry.enrollment_id}
                  className="border-b border-[var(--color-border)] last:border-b-0"
                >
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2.5">
                      <span
                        aria-hidden="true"
                        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[11px] font-semibold text-[var(--color-primary)]"
                      >
                        {initials(entry)}
                      </span>
                      <span className="font-medium text-[var(--color-text)]">
                        {entry.full_name || t("noName")}
                      </span>
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                    {entry.email}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                    {formatJoined(entry.enrolled_at)}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="secondary">{statusLabel(t, entry.status)}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {students.length > 0 ? (
        <p className="text-[12px] text-[var(--color-text-muted)]">
          {t("count", { count: students.length })}
        </p>
      ) : null}
    </section>
  );
}
