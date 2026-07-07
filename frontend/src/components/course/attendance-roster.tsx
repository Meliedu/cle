"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/patterns";
import {
  useMeetingAttendance,
  type AttendanceRosterEntry,
  type AttendanceStatus,
} from "@/hooks/use-checkpoints";

import { StatusChip, type StatusTone } from "./session-status";
import { AttendanceOverrideDialog } from "./attendance-override-dialog";

interface AttendanceRosterProps {
  readonly meetingId: string;
}

/** Attendance status → one shared tone (present reads done, absent muted). */
function attendanceTone(status: AttendanceStatus): StatusTone {
  switch (status) {
    case "present":
      return "success";
    case "late":
      return "progress";
    case "excused":
      return "info";
    case "absent":
    default:
      return "muted";
  }
}

/**
 * T047 — attendance roster result. The teacher's per-session attendance view:
 * present / late / excused / absent tallies over a row per active student.
 * Derived-absent rows (no `attendance_id` — a student who never scanned) render
 * with the override disabled, since there is no record to patch; every recorded
 * row can be manually overridden with a required reason (the dialog).
 */
export function AttendanceRoster({ meetingId }: AttendanceRosterProps) {
  const t = useTranslations("teacher.attendance");
  const { data, isLoading } = useMeetingAttendance(meetingId);
  const [target, setTarget] = useState<AttendanceRosterEntry | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full rounded-[var(--radius-xl)]" />
        <Skeleton className="h-40 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (!data || data.entries.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  const tallies: readonly { key: AttendanceStatus; count: number }[] = [
    { key: "present", count: data.present_count },
    { key: "late", count: data.late_count },
    { key: "excused", count: data.excused_count },
    { key: "absent", count: data.absent_count },
  ];

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {tallies.map((tally) => (
          <div
            key={tally.key}
            className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5"
          >
            <p className="text-[22px] font-bold leading-none tabular-nums text-[var(--color-text)]">
              {tally.count}
            </p>
            <p className="mt-1 text-[12px] text-[var(--color-text-muted)]">
              {t(`status.${tally.key}`)}
            </p>
          </div>
        ))}
      </div>

      <ul className="space-y-2">
        {data.entries.map((entry) => {
          const canOverride = entry.attendance_id !== null;
          return (
            <li
              key={entry.user_id}
              className="flex items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
                  {entry.full_name || entry.email}
                </p>
                <p className="truncate text-[12px] text-[var(--color-text-muted)]">
                  {entry.override_reason
                    ? t("overriddenNote", { reason: entry.override_reason })
                    : entry.email}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StatusChip
                  tone={attendanceTone(entry.status)}
                  label={t(`status.${entry.status}`)}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={!canOverride}
                  title={canOverride ? undefined : t("cannotOverride")}
                  onClick={() => setTarget(entry)}
                >
                  {t("override.trigger")}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      {target ? (
        <AttendanceOverrideDialog
          open={target !== null}
          onOpenChange={(open) => {
            if (!open) setTarget(null);
          }}
          meetingId={meetingId}
          entry={target}
        />
      ) : null}
    </section>
  );
}
