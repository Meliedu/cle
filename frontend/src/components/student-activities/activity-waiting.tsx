"use client";

import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/patterns";

/**
 * S053 — the "waiting for your instructor to start" state. Shown when an
 * activity exists but is not yet accepting responses: the read returned a
 * non-open status, or a submit was refused with the typed `ACTIVITY_NOT_OPEN`
 * (409). Never a blank panel — always the designed `waiting` EmptyState.
 */
export function ActivityWaiting() {
  const t = useTranslations("student.activities.waiting");
  return (
    <EmptyState variant="waiting" title={t("title")} reason={t("reason")} />
  );
}
