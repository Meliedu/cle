"use client";

import { useTranslations } from "next-intl";

import { PageHeader } from "@/components/patterns";
import { CalendarShell } from "@/components/calendar";

/**
 * Calendar page composition shared by every role lane. Wraps the full
 * month/week calendar surface (F8) — meetings + assignments + work_items merged
 * across every course the signed-in user can see, with an event-detail drawer.
 */
export function CalendarView() {
  const t = useTranslations("patterns.calendar");

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:px-10 md:py-10">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <CalendarShell />
    </div>
  );
}
