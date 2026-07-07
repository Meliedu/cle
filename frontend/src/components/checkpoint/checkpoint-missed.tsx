"use client";

import { CalendarX2, ListX } from "lucide-react";
import { useFormatter, useTranslations } from "next-intl";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";

interface CheckpointMissedProps {
  /** How many of the checkpoint's live cards the student submitted (0 = fully missed). */
  readonly submittedCount: number;
  /** Total live cards in the closed checkpoint. */
  readonly totalCount: number;
  /** ISO close timestamp, when known. */
  readonly closedAt: string | null;
  /** Whether attendance was recorded (late submission) vs missed entirely. */
  readonly attendanceRecorded: boolean;
  readonly onBackToSession: () => void;
  readonly onViewHistory: () => void;
}

/**
 * S038 — the missed / late terminal. Shown when a student opens a checkpoint
 * whose window has already closed. A warning banner explains the window ended,
 * a short receipt states whether attendance was recorded and how many cards
 * made it in, and a help note points to the instructor for corrections.
 */
export function CheckpointMissed({
  submittedCount,
  totalCount,
  closedAt,
  attendanceRecorded,
  onBackToSession,
  onViewHistory,
}: CheckpointMissedProps) {
  const t = useTranslations("student.checkpoint.missed");
  const format = useFormatter();

  return (
    <div className="space-y-6">
      <StateBanner tone="warning" title={t("title")} reason={t("reason")} />

      <ul className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <Row
          icon={CalendarX2}
          label={
            attendanceRecorded ? t("attendanceLate") : t("attendanceNot")
          }
        />
        <Row
          icon={ListX}
          label={t("submitted", {
            count: submittedCount,
            total: totalCount,
          })}
        />
        {closedAt ? (
          <Row
            icon={CalendarX2}
            label={t("closedAt", {
              time: format.dateTime(new Date(closedAt), {
                hour: "numeric",
                minute: "2-digit",
              }),
            })}
          />
        ) : null}
      </ul>

      <div className="flex flex-col gap-2">
        <Button type="button" size="lg" onClick={onBackToSession}>
          {t("backToSession")}
        </Button>
        <Button type="button" size="lg" variant="ghost" onClick={onViewHistory}>
          {t("viewHistory")}
        </Button>
      </div>

      <p className="text-center text-[12px] text-[var(--color-text-muted)]">
        {t("help")}
      </p>
    </div>
  );
}

function Row({
  icon: Icon,
  label,
}: {
  readonly icon: typeof CalendarX2;
  readonly label: string;
}) {
  return (
    <li className="flex items-center gap-2.5 text-[13px] text-[var(--color-text-secondary)]">
      <Icon
        aria-hidden="true"
        strokeWidth={1.85}
        className="size-4 shrink-0 text-[var(--color-text-muted)]"
      />
      {label}
    </li>
  );
}
