"use client";

import { useTranslations } from "next-intl";

import { StateBanner, EmptyState } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useActivityResults,
  type ActivityFormat,
  type ActivityResponseRecord,
} from "@/hooks/use-activities";

interface ActivityResultsProps {
  readonly activityId: string;
  /** When true, hide student identities in the evidence table. */
  readonly anonymous?: boolean;
}

/**
 * T073 — teacher results / evidence view over `useActivityResults`. Renders the
 * total submission count and a per-response evidence table with each student's
 * format-specific answer. Honors `anonymous` by masking identities. Designed
 * loading / empty / error states (never blank).
 */
export function ActivityResults({ activityId, anonymous = false }: ActivityResultsProps) {
  const t = useTranslations("teacher.activities.results");
  const { data, isLoading, isError } = useActivityResults(activityId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-11 w-full rounded-[var(--radius-md)]" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("title")}
          </h3>
          <span className="text-[13px] tabular-nums text-[var(--color-text-secondary)]">
            {t("submissionCount", { count: data.submission_count })}
          </span>
        </div>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {anonymous ? t("anonymousNote") : t("description")}
        </p>
      </header>

      {data.responses.length === 0 ? (
        <EmptyState title={t("empty.title")} reason={t("empty.reason")} />
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--color-border)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[12px] uppercase tracking-wide text-[var(--color-text-muted)]">
                <th className="px-4 py-2.5 font-medium">{t("columns.student")}</th>
                <th className="px-4 py-2.5 font-medium">{t("columns.response")}</th>
                <th className="px-4 py-2.5 font-medium">{t("columns.submittedAt")}</th>
              </tr>
            </thead>
            <tbody>
              {data.responses.map((response) => (
                <tr
                  key={response.id}
                  className="border-b border-[var(--color-border)]/60 last:border-0"
                >
                  <td className="px-4 py-2.5 text-[var(--color-text)]">
                    {anonymous ? t("anonymousStudent") : response.user_id}
                  </td>
                  <td className="px-4 py-2.5 text-[var(--color-text-secondary)]">
                    {formatResponse(data.format, response, (k) => t(`swipe.${k}`))}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-[var(--color-text-muted)]">
                    {formatTimestamp(response.submitted_at)}
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

/** Render a response's per-format payload as a short human string. */
function formatResponse(
  format: ActivityFormat,
  response: ActivityResponseRecord,
  swipeLabel: (key: "left" | "right") => string
): string {
  const payload = response.payload as Record<string, unknown>;
  if (format === "swipe") {
    const direction = payload.direction === "right" ? "right" : "left";
    return swipeLabel(direction);
  }
  if (format === "vote") {
    return typeof payload.choice === "string" ? payload.choice : "—";
  }
  if (format === "comment_reaction") {
    return typeof payload.reaction === "string" ? payload.reaction : "—";
  }
  return "—";
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
