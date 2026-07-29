"use client";

import { useTranslations } from "next-intl";

import { CalendarShell } from "@/components/calendar";

/**
 * Calendar page composition shared by every role lane.
 *
 * The page header carries identity and the one page-level action; the
 * `CalendarShell` owns period navigation, view mode, and filters, all inside
 * the grid card, per Plate 03 rule 1. Nothing here duplicates a control the
 * shell already provides.
 */
export function CalendarView() {
  const t = useTranslations("patterns.calendar");

  return (
    <div className="mx-auto w-full max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[34px]">
            {t("title")}
          </h1>
          <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
      </header>

      <CalendarShell />
    </div>
  );
}
