"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { CalendarDays } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { StatusChip, releaseTone } from "@/components/course/session-status";
import { useMeetings, type Meeting } from "@/hooks/use-meetings";

interface StudentScheduleTableProps {
  readonly courseId: string;
}

/** Locale date for a session, e.g. "Fri, 10 Jul". */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

/** Locale time for a session, e.g. "10:30". */
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * S025 — student class schedule. A read-only mirror of the teacher schedule
 * table: every session for the course by index, with date, time, venue, topic,
 * and its student-visibility `release_state` shown as one status chip. Students
 * cannot edit; the class schedule is generated from the instructor's setup.
 */
export function StudentScheduleTable({ courseId }: StudentScheduleTableProps) {
  const t = useTranslations("student.schedule");
  const { data, isLoading, isError } = useMeetings(courseId);

  const meetings = useMemo<readonly Meeting[]>(
    () => (data ? [...data].sort((a, b) => a.meeting_index - b.meeting_index) : []),
    [data]
  );

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

      {isError ? (
        <StateBanner
          tone="warning"
          title={t("error.title")}
          reason={t("error.reason")}
        />
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : meetings.length === 0 ? (
        <EmptyState
          icon={CalendarDays}
          title={t("empty.title")}
          reason={t("empty.reason")}
        />
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--color-border)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[12px] uppercase tracking-wide text-[var(--color-text-muted)]">
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.session")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.date")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.time")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.venue")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.topic")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.status")}
                </th>
              </tr>
            </thead>
            <tbody>
              {meetings.map((m) => (
                <tr
                  key={m.id}
                  className="border-b border-[var(--color-border)] last:border-b-0"
                >
                  <td className="px-4 py-3 font-semibold text-[var(--color-text)]">
                    {m.meeting_index}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                    {formatDate(m.scheduled_at)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                    {formatTime(m.scheduled_at)}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                    {m.location || t("placeholder")}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text)]">
                    {m.topic_summary || m.title || t("placeholder")}
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip
                      tone={releaseTone(m.release_state)}
                      label={t(`release.${m.release_state}`)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
