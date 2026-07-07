"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CircleCheckBig, Radio, WifiOff } from "lucide-react";

import { useAuth } from "@/hooks/use-auth";
import { useCheckpointMonitor } from "@/hooks/use-checkpoints";

interface CheckpointMonitorProps {
  readonly checkpointId: string;
  /** Only opens the socket while the checkpoint is actually live. */
  readonly enabled: boolean;
}

/** The −2..+2 confidence buckets, ordered low → high for the bar chart. */
const CONFIDENCE_KEYS = ["-2", "-1", "0", "1", "2"] as const;

/**
 * T046 — live checkpoint monitor. Consumes the `useCheckpointMonitor` WS stream
 * (which reuses the live-quiz hub) and renders the running submission count, a
 * −2..+2 confidence distribution as horizontal bars, and a terminal "closed"
 * state once the checkpoint ends. The monitor authenticates the socket with the
 * teacher's backend JWT (resolved once on mount), mirroring the live-quiz
 * client. Read-only — it never sends frames.
 */
export function CheckpointMonitor({ checkpointId, enabled }: CheckpointMonitorProps) {
  const t = useTranslations("teacher.checkpoint.monitor");
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

  const state = useCheckpointMonitor(
    enabled ? checkpointId : null,
    enabled ? wsToken : null
  );

  const maxBucket = Math.max(
    1,
    ...CONFIDENCE_KEYS.map((k) => state.confidence_distribution[k] ?? 0)
  );

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

      <div className="space-y-2" aria-label={t("distributionLabel")}>
        {CONFIDENCE_KEYS.map((key) => {
          const count = state.confidence_distribution[key] ?? 0;
          const pct = Math.round((count / maxBucket) * 100);
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-8 shrink-0 text-right text-[12px] font-medium tabular-nums text-[var(--color-text-secondary)]">
                {key}
              </span>
              <div className="h-3 flex-1 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]">
                <div
                  className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)]"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-[12px] tabular-nums text-[var(--color-text-muted)]">
                {count}
              </span>
            </div>
          );
        })}
      </div>

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
