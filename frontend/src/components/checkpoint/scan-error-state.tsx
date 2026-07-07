"use client";

import { useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

interface ScanErrorStateProps {
  /** The error thrown by `useScanAttendance` — inspected for its typed `code`. */
  readonly error: unknown;
  /** Re-run the scan (only meaningful for transient failures like rate-limits). */
  readonly onRetry: () => void;
  /** Leave the scan flow (back to the student's courses). */
  readonly onBackToCourses: () => void;
}

type ScanErrorKind = "invalid" | "closed" | "rate_limited" | "generic";

/**
 * Map the backend's typed scan-error `code` (with an HTTP-status fallback) to a
 * UI kind. 401 `LAUNCH_TOKEN_INVALID`, 409 `LAUNCH_CLOSED`, 429 `RATE_LIMITED`
 * per the attendance router (P3 T10); anything else is a generic failure.
 */
function classify(error: unknown): ScanErrorKind {
  if (error instanceof ApiError) {
    if (error.code === "LAUNCH_TOKEN_INVALID" || error.status === 401)
      return "invalid";
    if (error.code === "LAUNCH_CLOSED" || error.status === 409) return "closed";
    if (error.code === "RATE_LIMITED" || error.status === 429)
      return "rate_limited";
  }
  return "generic";
}

/**
 * S033 (error) — the designed failure state for a QR scan. Only a rate-limited
 * scan is worth retrying, so the retry action is shown for that kind alone; the
 * others offer a way back to the student's courses. Mobile-first single column.
 */
export function ScanErrorState({
  error,
  onRetry,
  onBackToCourses,
}: ScanErrorStateProps) {
  const t = useTranslations("student.checkpoint.scan.error");
  const kind = classify(error);
  const tone = kind === "rate_limited" ? "waiting" : "warning";

  return (
    <div className="space-y-6">
      <StateBanner
        tone={tone}
        title={t(`${kind}.title`)}
        reason={t(`${kind}.reason`)}
      />

      <div className="flex flex-col gap-2">
        {kind === "rate_limited" ? (
          <Button type="button" size="lg" onClick={onRetry}>
            {t("retry")}
          </Button>
        ) : null}
        <Button
          type="button"
          size="lg"
          variant={kind === "rate_limited" ? "ghost" : "default"}
          onClick={onBackToCourses}
        >
          {t("backToCourses")}
        </Button>
      </div>
    </div>
  );
}
