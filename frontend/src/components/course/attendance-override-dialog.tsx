"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  useOverrideAttendance,
  type AttendanceRosterEntry,
  type AttendanceStatus,
} from "@/hooks/use-checkpoints";

const STATUSES: readonly AttendanceStatus[] = [
  "present",
  "late",
  "excused",
  "absent",
];

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";

interface AttendanceOverrideDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly meetingId: string;
  /** The roster entry being overridden — must carry a non-null `attendance_id`. */
  readonly entry: AttendanceRosterEntry;
}

/**
 * T047 — manual attendance override modal. A teacher corrects one student's
 * status (e.g. marking a genuine absence excused). The `override_reason` is
 * required — the confirm button stays disabled until a non-empty reason is
 * entered, mirroring the backend's 422 on a blank reason. Only ever opened for
 * entries that already have an `attendance_id` (a derived-absent row has no
 * record to patch), so the caller gates the trigger.
 */
export function AttendanceOverrideDialog({
  open,
  onOpenChange,
  meetingId,
  entry,
}: AttendanceOverrideDialogProps) {
  const t = useTranslations("teacher.attendance.override");
  const override = useOverrideAttendance(meetingId);
  const [status, setStatus] = useState<AttendanceStatus>(entry.status);
  const [reason, setReason] = useState("");
  const [error, setError] = useState(false);

  const reasonMissing = reason.trim().length === 0;

  const confirm = useCallback(async () => {
    if (reasonMissing || !entry.attendance_id) return;
    setError(false);
    try {
      await override.mutateAsync({
        attendanceId: entry.attendance_id,
        status,
        override_reason: reason.trim(),
      });
      onOpenChange(false);
    } catch {
      setError(true);
    }
  }, [override, entry.attendance_id, status, reason, reasonMissing, onOpenChange]);

  const name = entry.full_name || entry.email;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle", { name })}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label
              htmlFor="override-status"
              className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("statusLabel")}
            </label>
            <select
              id="override-status"
              className={SELECT_CLASS}
              value={status}
              onChange={(e) => setStatus(e.target.value as AttendanceStatus)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {t(`status.${s}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="override-reason"
              className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("reasonLabel")}
            </label>
            <Textarea
              id="override-reason"
              rows={2}
              value={reason}
              placeholder={t("reasonPlaceholder")}
              aria-invalid={reasonMissing}
              onChange={(e) => setReason(e.target.value)}
            />
            <p className="text-[12px] text-[var(--color-text-muted)]">
              {t("reasonHint")}
            </p>
          </div>

          {error ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {t("error")}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            disabled={override.isPending || reasonMissing}
            onClick={() => void confirm()}
          >
            {override.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : null}
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
