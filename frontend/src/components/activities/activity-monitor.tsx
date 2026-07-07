"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CircleCheckBig, Radio, WifiOff } from "lucide-react";

import { useAuth } from "@/hooks/use-auth";
import {
  useActivityMonitor,
  type ActivityDistribution,
  type ActivityFormat,
} from "@/hooks/use-activities";

interface ActivityMonitorProps {
  readonly activityId: string;
  readonly format: ActivityFormat;
  /** Only opens the socket while the activity is actually live. */
  readonly enabled: boolean;
}

/**
 * T072 — live activity monitor. Consumes the `useActivityMonitor` WS stream
 * (mirroring the checkpoint monitor) and renders the running submission count
 * plus a format-specific aggregate built from `distribution`:
 *
 *  - swipe → a left / right split bar,
 *  - vote → a tally bar per option,
 *  - comment_reaction → a reaction histogram.
 *
 * The socket is authenticated with the teacher's backend JWT (resolved once on
 * mount). Read-only — it never sends frames. Bar growth uses
 * `motion-reduce:transition-none` so `prefers-reduced-motion` is respected.
 */
export function ActivityMonitor({ activityId, format, enabled }: ActivityMonitorProps) {
  const t = useTranslations("teacher.activities.monitor");
  const { getToken } = useAuth();
  const [wsToken, setWsToken] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    void getToken({ template: "backend" }).then((token) => {
      if (active) setWsToken(token);
    });
    return () => {
      active = false;
    };
  }, [enabled, getToken]);

  const state = useActivityMonitor(
    enabled ? activityId : null,
    enabled ? wsToken : null
  );

  const rows = distributionRows(format, state.distribution, (key) =>
    t(`swipe.${key}`)
  );
  const maxBucket = Math.max(1, ...rows.map((r) => r.count));

  return (
    <div className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("title")}
          </h3>
          <ConnectionDot
            closed={state.closed}
            connected={state.connected}
            label={
              state.closed
                ? t("status.closed")
                : state.connected
                  ? t("status.live")
                  : t("status.connecting")
            }
          />
        </div>
        <div className="text-right">
          <p className="text-[24px] font-bold leading-none tabular-nums text-[var(--color-text)]">
            {state.submission_count}
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("submissions")}
          </p>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-4 py-8 text-center">
          <p className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("empty.title")}
          </p>
          <p className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
            {t("empty.reason")}
          </p>
        </div>
      ) : (
        <div className="space-y-2" aria-label={t("distributionLabel")}>
          {rows.map((row) => {
            const pct = Math.round((row.count / maxBucket) * 100);
            return (
              <div key={row.key} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate text-right text-[12px] font-medium text-[var(--color-text-secondary)]">
                  {row.label}
                </span>
                <div className="h-3 flex-1 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]">
                  <div
                    className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)] motion-reduce:transition-none"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="w-6 shrink-0 text-[12px] tabular-nums text-[var(--color-text-muted)]">
                  {row.count}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {state.closed ? (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3 py-2.5 text-[13px] text-[var(--color-text-secondary)]">
          <CircleCheckBig
            aria-hidden="true"
            className="size-4 shrink-0 text-[var(--color-success)]"
          />
          {t("closedNotice")}
        </div>
      ) : null}
    </div>
  );
}

interface DistributionRow {
  readonly key: string;
  readonly label: string;
  readonly count: number;
}

/**
 * Build the ordered bar rows for a format's distribution. Swipe always shows
 * left then right (even at zero); vote / comment_reaction render one bar per
 * observed key, sorted for a stable order.
 */
function distributionRows(
  format: ActivityFormat,
  distribution: ActivityDistribution,
  swipeLabel: (key: "left" | "right") => string
): readonly DistributionRow[] {
  if (format === "swipe") {
    return [
      { key: "left", label: swipeLabel("left"), count: distribution.left ?? 0 },
      { key: "right", label: swipeLabel("right"), count: distribution.right ?? 0 },
    ];
  }
  return Object.entries(distribution)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, count]) => ({ key, label: key, count }));
}

interface ConnectionDotProps {
  readonly closed: boolean;
  readonly connected: boolean;
  readonly label: string;
}

function ConnectionDot({ closed, connected, label }: ConnectionDotProps) {
  const Icon = closed ? CircleCheckBig : connected ? Radio : WifiOff;
  const color = closed
    ? "text-[var(--color-success)]"
    : connected
      ? "text-[var(--color-primary)]"
      : "text-[var(--color-text-muted)]";
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-text-muted)]">
      <Icon aria-hidden="true" className={`size-3.5 ${color}`} />
      {label}
    </span>
  );
}
