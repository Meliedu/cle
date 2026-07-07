"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import { useMeetings, type Meeting, type ReleaseState } from "@/hooks/use-meetings";

interface CourseScheduleTableProps {
  readonly courseId: string;
}

/** Badge tone per release state — released/completed read as progress. */
function releaseVariant(
  state: ReleaseState
): "default" | "secondary" | "outline" {
  switch (state) {
    case "released":
      return "secondary";
    case "completed":
      return "default";
    default:
      return "outline";
  }
}

/** Locale date + time for a session, e.g. "Fri, 15 Jan · 10:30". */
function formatSession(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const time = date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${day} · ${time}`;
}

/**
 * T030 — read-only course schedule table. Lists every session for the course
 * via `useMeetings` (P1 `use-meetings.ts`): session number (`meeting_index`),
 * date/time, venue (`location`), topic (`topic_summary` → `title`), and the
 * student-visibility `release_state`. Editing lives in the setup schedule step,
 * so this view only reads — an "Edit in setup" link routes teachers there.
 */
export function CourseScheduleTable({ courseId }: CourseScheduleTableProps) {
  const t = useTranslations("teacher.course.schedule");
  const { data, isLoading } = useMeetings(courseId);
  const setupHref = `/teacher/courses/${courseId}/setup`;

  const meetings: readonly Meeting[] = data
    ? [...data].sort((a, b) => a.meeting_index - b.meeting_index)
    : [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <Button size="sm" variant="outline" render={<Link href={setupHref} />}>
          {t("editInSetup")}
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : meetings.length === 0 ? (
        <EmptyState
          title={t("empty.title")}
          reason={t("empty.reason")}
          action={
            <Button size="sm" variant="outline" render={<Link href={setupHref} />}>
              {t("editInSetup")}
            </Button>
          }
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
                  {t("columns.venue")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.topic")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.release")}
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
                    {formatSession(m.scheduled_at)}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text-secondary)]">
                    {m.location || t("placeholder")}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-text)]">
                    {m.topic_summary || m.title || t("placeholder")}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={releaseVariant(m.release_state)}>
                      {t(`release.${m.release_state}`)}
                    </Badge>
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
