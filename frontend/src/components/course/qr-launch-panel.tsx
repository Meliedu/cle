"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { QRCodeSVG } from "qrcode.react";
import { Loader2, QrCode, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import { ApiError } from "@/lib/api";
import {
  useLaunchCheckpoint,
  type CheckpointLaunch,
} from "@/hooks/use-checkpoints";

interface QrLaunchPanelProps {
  readonly checkpointId: string;
}

/** Remaining whole seconds until an ISO instant, floored at 0. */
function secondsUntil(iso: string): number {
  return Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000));
}

/** Live seconds-remaining until `windowEnd`, re-derived every second. */
function useCountdown(windowEnd: string | null): number {
  const [remaining, setRemaining] = useState(() =>
    windowEnd ? secondsUntil(windowEnd) : 0
  );
  useEffect(() => {
    if (!windowEnd) {
      setRemaining(0);
      return;
    }
    setRemaining(secondsUntil(windowEnd));
    const id = setInterval(() => setRemaining(secondsUntil(windowEnd)), 1000);
    return () => clearInterval(id);
  }, [windowEnd]);
  return remaining;
}

/** `125` → `"2:05"`. */
function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Origin-qualified deep link a student's camera opens to record the scan. */
function attendUrl(token: string): string {
  const origin =
    typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/student/attend/${encodeURIComponent(token)}`;
}

/**
 * T045 — QR launch panel. Mints a signed, window-bound attendance launch
 * (`useLaunchCheckpoint`) and renders its token as a scannable QR (a deep link
 * into the student attend route) alongside a live countdown to `window_end`. A
 * "rotate" action closes the prior launch and issues a fresh token. A 409
 * `QR_NOT_AVAILABLE` (the checkpoint isn't a session-bound published/live
 * checkpoint with QR enabled) surfaces as a blocked banner.
 */
export function QrLaunchPanel({ checkpointId }: QrLaunchPanelProps) {
  const t = useTranslations("teacher.checkpoint.qr");
  const launchMutation = useLaunchCheckpoint(checkpointId);
  const [launch, setLaunch] = useState<CheckpointLaunch | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [genericError, setGenericError] = useState(false);

  const remaining = useCountdown(launch?.window_end ?? null);
  const expired = launch !== null && remaining <= 0;

  const run = useCallback(
    async (rotate: boolean) => {
      setBlocked(null);
      setGenericError(false);
      try {
        const result = await launchMutation.mutateAsync({ rotate });
        setLaunch(result);
      } catch (error) {
        if (error instanceof ApiError && error.code === "QR_NOT_AVAILABLE") {
          setBlocked(error.detail ?? t("unavailableReason"));
        } else {
          setGenericError(true);
        }
      }
    },
    [launchMutation, t]
  );

  if (blocked) {
    return (
      <StateBanner tone="blocked" title={t("unavailableTitle")} reason={blocked} />
    );
  }

  if (!launch) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-8 text-center">
        <QrCode
          aria-hidden="true"
          strokeWidth={1.6}
          className="size-8 text-[var(--color-text-muted)]"
        />
        <div className="space-y-1">
          <p className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("launchTitle")}
          </p>
          <p className="max-w-[38ch] text-[13px] text-[var(--color-text-secondary)]">
            {t("launchReason")}
          </p>
        </div>
        <Button
          type="button"
          disabled={launchMutation.isPending}
          onClick={() => void run(false)}
        >
          {launchMutation.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <QrCode aria-hidden="true" />
          )}
          {t("launch")}
        </Button>
        {genericError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {t("generic")}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-center">
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-white p-3">
        <QRCodeSVG
          value={attendUrl(launch.token)}
          size={192}
          level="M"
          aria-label={t("qrAlt")}
        />
      </div>

      <div
        className="space-y-1"
        role="status"
        aria-live="polite"
      >
        {expired ? (
          <p className="text-[14px] font-semibold text-[var(--color-warning)]">
            {t("expired")}
          </p>
        ) : (
          <>
            <p className="text-[22px] font-bold tabular-nums tracking-tight text-[var(--color-text)]">
              {formatDuration(remaining)}
            </p>
            <p className="text-[12px] text-[var(--color-text-muted)]">
              {t("countdownLabel")}
            </p>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          disabled={launchMutation.isPending}
          onClick={() => void run(true)}
        >
          {launchMutation.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <RefreshCw aria-hidden="true" />
          )}
          {t("rotate")}
        </Button>
      </div>

      <p className="max-w-[42ch] break-all text-[11px] text-[var(--color-text-muted)]">
        {t("fallbackLabel")}: {attendUrl(launch.token)}
      </p>

      {genericError ? (
        <p role="alert" className="text-[13px] text-[var(--color-error)]">
          {t("generic")}
        </p>
      ) : null}
    </div>
  );
}
