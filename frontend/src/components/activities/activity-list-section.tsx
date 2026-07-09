"use client";

import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner, EmptyState } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { useActivities, type Activity, type ActivityFormat, type ActivityStatus } from "@/hooks/use-activities";

import { ACTIVITY_FORMAT_META, ACTIVITY_FORMATS } from "./activity-format";

interface ActivityListSectionProps {
  readonly courseId: string;
  readonly onNew: (format: ActivityFormat) => void;
  readonly onSelect: (activity: Activity) => void;
}

/**
 * F6 in-class activities list. Renders every authored activity with its format,
 * status, and score-bearing badge, plus a per-format "new" control. Designed
 * loading / empty / error states.
 */
export function ActivityListSection({ courseId, onNew, onSelect }: ActivityListSectionProps) {
  const t = useTranslations("teacher.activities.home");
  const tf = useTranslations("teacher.activities.formats");
  const { data, isLoading, isError } = useActivities(courseId);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[16px] font-semibold text-[var(--color-text)]">
          {t("sections.activities")}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {ACTIVITY_FORMATS.map((format) => {
            const meta = ACTIVITY_FORMAT_META[format];
            return (
              <Button
                key={format}
                type="button"
                variant="outline"
                size="sm"
                onClick={() => onNew(format)}
                className="border-[var(--color-primary-muted)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)] hover:border-[var(--color-primary)] hover:bg-[var(--color-primary-muted)] hover:text-[var(--color-primary-hover)]"
              >
                <Plus />
                {t("newFormat", { format: tf(meta.labelKey) })}
              </Button>
            );
          })}
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-14 w-full rounded-[var(--radius-lg)]" />
          ))}
        </div>
      ) : isError ? (
        <StateBanner tone="warning" title={t("error.title")} reason={t("error.reason")} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          className="rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)]"
          title={t("emptyActivities.title")}
          reason={t("emptyActivities.reason")}
        />
      ) : (
        <ul className="space-y-2">
          {data.map((activity) => (
            <li key={activity.id}>
              <button
                type="button"
                onClick={() => onSelect(activity)}
                className="flex w-full items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left transition-colors hover:border-[var(--color-primary)]/50 hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40"
              >
                {(() => {
                  const Icon = ACTIVITY_FORMAT_META[activity.format].Icon;
                  return (
                    <Icon
                      aria-hidden="true"
                      className="size-4 shrink-0 text-[var(--color-primary)]"
                    />
                  );
                })()}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-medium text-[var(--color-text)]">
                    {activity.title}
                  </span>
                  <span className="text-[12px] text-[var(--color-text-muted)]">
                    {tf(ACTIVITY_FORMAT_META[activity.format].labelKey)}
                  </span>
                </span>
                {activity.score_bearing ? (
                  <span className="shrink-0 rounded-[var(--radius-pill)] border border-[var(--color-primary)]/40 bg-[var(--color-accent-light)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-primary-hover)]">
                    {t("scoreBearing")}
                  </span>
                ) : (
                  <span className="shrink-0 text-[11px] text-[var(--color-text-muted)]">
                    {t("participation")}
                  </span>
                )}
                <StatusBadge status={activity.status} label={t(`status.${activity.status}`)} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface StatusBadgeProps {
  readonly status: ActivityStatus;
  readonly label: string;
}

function StatusBadge({ status, label }: StatusBadgeProps) {
  const tone =
    status === "live"
      ? "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]"
      : status === "published"
        ? "border-[var(--color-primary)]/40 bg-[var(--color-accent-light)] text-[var(--color-primary-hover)]"
        : status === "closed" || status === "archived"
          ? "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]"
          : "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-hover)]";
  return (
    <span
      className={`shrink-0 rounded-[var(--radius-pill)] border px-2 py-0.5 text-[11px] font-medium ${tone}`}
    >
      {label}
    </span>
  );
}
