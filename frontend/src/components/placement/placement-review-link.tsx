"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, ClipboardCheck } from "lucide-react";

import { cn } from "@/lib/utils";
import { usePlacementQueue } from "@/hooks/use-placement";

/**
 * Entry point to the placement review queue, for the teacher Insights page.
 *
 * Placement review does not get a global rail slot: the approved handoff fixes
 * the teacher rail at Home, Courses, Calendar, Insights, and `nav-config.test`
 * pins that. Insights is where the wireframes put placement review, so it is
 * reached from there.
 *
 * Renders nothing when there is no published test or nothing waiting. A
 * permanent zero card would train reviewers to ignore the one place that tells
 * them a student is waiting on a decision.
 */
export function PlacementReviewLink() {
  const t = useTranslations("teacher.placement");
  const queue = usePlacementQueue();

  const data = queue.data;
  const waiting = (data?.needs_review ?? 0) + (data?.ready_to_approve ?? 0);
  if (queue.isError || !data || waiting === 0) return null;

  const blocked = data.blocked > 0;

  return (
    <Link
      href="/teacher/placement"
      className={cn(
        "flex items-center gap-4 rounded-[var(--radius-xl)] border bg-[var(--color-surface)] p-5",
        "outline-none transition-colors duration-150",
        "hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40",
        blocked ? "border-[var(--color-error)]/40" : "border-[var(--color-border)]"
      )}
    >
      <span
        aria-hidden="true"
        className="inline-flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)] bg-[var(--color-primary)]/10 text-[var(--color-primary-hover)]"
      >
        <ClipboardCheck className="size-5" strokeWidth={1.9} />
      </span>
      <span className="flex-1">
        <span className="block text-[15px] font-semibold text-[var(--color-text)]">
          {t("linkTitle")}
        </span>
        <span className="block text-[14px] text-[var(--color-text-secondary)]">
          {blocked
            ? t("linkReasonBlocked", { waiting, blocked: data.blocked })
            : t("linkReason", { waiting })}
        </span>
      </span>
      <ArrowRight
        aria-hidden="true"
        className="size-4 shrink-0 text-[var(--color-text-secondary)]"
      />
    </Link>
  );
}
