"use client";

import { CheckCircle2, Clock, DoorOpen } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import type { AttendanceStatus } from "@/hooks/use-checkpoints";

interface AttendanceConfirmedProps {
  /** Recorded attendance status (present / late). */
  readonly status: AttendanceStatus;
  /** ISO check-in timestamp. */
  readonly checkedInAt: string | null;
  /** Whether the student also submitted the checkpoint (adds a receipt line). */
  readonly submitted?: boolean;
  readonly onBackToSession: () => void;
  /** Optional secondary action to review the submitted response. */
  readonly onViewResponse?: () => void;
}

/**
 * S042 — attendance confirmed. The terminal shown when a scan records
 * attendance but there's nothing (further) to answer — e.g. a re-scan or a
 * checkpoint with no live cards. A success mark, the recorded status + time,
 * and a way back. Names/room aren't in the scan payload, so this receipt stays
 * to the facts we hold (status + time).
 */
export function AttendanceConfirmed({
  status,
  checkedInAt,
  submitted = false,
  onBackToSession,
  onViewResponse,
}: AttendanceConfirmedProps) {
  const t = useTranslations("student.checkpoint.confirmed");
  const format = useFormatter();

  return (
    <div className="space-y-6 text-center">
      <div className="flex flex-col items-center gap-3">
        <div className="flex size-16 items-center justify-center rounded-full border border-[var(--color-success)]/40 bg-[var(--color-success-light)]">
          <CheckCircle2
            aria-hidden="true"
            strokeWidth={1.75}
            className="size-8 text-[var(--color-success)]"
          />
        </div>
        <div className="space-y-1.5">
          <h1 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h1>
          <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("reason")}
          </p>
        </div>
      </div>

      <ul className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-left">
        <Row
          icon={DoorOpen}
          label={t("statusLabel", { status: t(`statusValue.${status}`) })}
        />
        {checkedInAt ? (
          <Row
            icon={Clock}
            label={t("checkedInAt", {
              time: format.dateTime(new Date(checkedInAt), {
                hour: "numeric",
                minute: "2-digit",
              }),
            })}
          />
        ) : null}
        {submitted ? <Row icon={CheckCircle2} label={t("submittedChip")} /> : null}
      </ul>

      <div className="flex flex-col gap-2">
        <Button type="button" size="lg" onClick={onBackToSession}>
          {t("backToSession")}
        </Button>
        {onViewResponse ? (
          <Button
            type="button"
            size="lg"
            variant="ghost"
            onClick={onViewResponse}
          >
            {t("viewResponse")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Row({
  icon: Icon,
  label,
}: {
  readonly icon: typeof Clock;
  readonly label: string;
}) {
  return (
    <li className="flex items-center gap-2.5 text-[13px] text-[var(--color-text-secondary)]">
      <Icon
        aria-hidden="true"
        strokeWidth={1.85}
        className="size-4 shrink-0 text-[var(--color-success)]"
      />
      {label}
    </li>
  );
}
