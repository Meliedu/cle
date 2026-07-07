"use client";

import { useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/patterns";
import {
  useScanAttendance,
  type AttendanceStatus,
} from "@/hooks/use-checkpoints";

import { CheckpointRunner } from "./checkpoint-runner";
import { ScanErrorState } from "./scan-error-state";

interface CheckpointAttendProps {
  /** The signed launch token from the QR deep link (`/student/attend/{token}`). */
  readonly token: string;
}

const COURSES_ROUTE = "/student/courses";

/**
 * S033 — the QR scan landing. On mount it posts the launch token to
 * `POST /attend/{token}` exactly once; while the scan is in flight it shows a
 * waiting state. A successful scan records attendance server-side and returns
 * the `checkpoint_id`, which we hand to `CheckpointRunner` to drive the intro →
 * confidence → comments → complete flow (S034–S037). Typed scan failures
 * (401/409/429) fall through to the designed `ScanErrorState`.
 *
 * NB: the backend's `intro_route` is an API path (`/api/checkpoints/{id}/intro`),
 * not a client route — so we drive the flow inline off `checkpoint_id` rather
 * than navigating to it, keeping the whole check-in on one mobile screen.
 */
export function CheckpointAttend({ token }: CheckpointAttendProps) {
  const t = useTranslations("student.checkpoint.scan");
  const router = useRouter();
  const scan = useScanAttendance();

  // Fire the scan a single time on mount (React Strict Mode double-invokes
  // effects in dev; the ref guard keeps it to one real POST).
  const scanMutate = scan.mutate;
  const firedRef = useRef(false);
  const runScan = useCallback(() => {
    scanMutate({ token });
  }, [scanMutate, token]);

  useEffect(() => {
    if (firedRef.current) return;
    firedRef.current = true;
    runScan();
  }, [runScan]);

  const backToCourses = useCallback(() => {
    router.push(COURSES_ROUTE);
  }, [router]);

  const retry = useCallback(() => {
    scan.reset();
    runScan();
  }, [runScan, scan]);

  if (scan.isError) {
    return (
      <ScanErrorState
        error={scan.error}
        onRetry={retry}
        onBackToCourses={backToCourses}
      />
    );
  }

  if (scan.isSuccess) {
    return (
      <CheckpointRunner
        checkpointId={scan.data.checkpoint_id}
        attendance={{
          status: scan.data.status as AttendanceStatus,
          checkedInAt: scan.data.checked_in_at,
        }}
        onExit={backToCourses}
        onViewHistory={backToCourses}
      />
    );
  }

  // idle | pending — the POST is in flight.
  return (
    <EmptyState
      variant="waiting"
      title={t("scanning")}
      reason={t("scanningReason")}
    />
  );
}
