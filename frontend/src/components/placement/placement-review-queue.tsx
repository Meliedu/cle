"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, Inbox } from "lucide-react";

import { EmptyState, PageHeader } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { usePlacementQueue, type PlacementQueueItem } from "@/hooks/use-placement";

import { flagSeverity, hasBlockingFlag, sortFlags } from "./review-flags";

/**
 * The CLE placement review queue (wireframe T094).
 *
 * Three counts, then the work. "Blocked" is deliberately separate from "needs
 * review": a blocked attempt cannot be approved at all until someone fixes the
 * content or the form, so folding it into the review count would let a reviewer
 * spend time on something no decision can resolve.
 */
export function PlacementReviewQueue() {
  const t = useTranslations("teacher.placement");
  const queue = usePlacementQueue();

  if (queue.isLoading) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6 py-2" aria-busy="true">
        <PageHeader title={t("title")} description={t("subtitle")} />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
        <span className="sr-only">{t("loading")}</span>
      </div>
    );
  }

  const data = queue.data;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 py-2">
      <PageHeader title={t("title")} description={t("subtitle")} />

      <dl className="grid gap-3 sm:grid-cols-3">
        <Count label={t("needsReview")} value={data?.needs_review ?? 0} />
        <Count label={t("readyToApprove")} value={data?.ready_to_approve ?? 0} />
        <Count
          label={t("blocked")}
          value={data?.blocked ?? 0}
          tone={(data?.blocked ?? 0) > 0 ? "danger" : "default"}
        />
      </dl>

      {!data || data.items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title={t("emptyTitle")}
          reason={t("emptyReason")}
        />
      ) : (
        <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          <h2 className="border-b border-[var(--color-border)] px-5 py-4 text-[15px] font-semibold text-[var(--color-text)]">
            {t("queueTitle")}
          </h2>
          <ul>
            {data.items.map((item) => (
              <QueueRow key={item.attempt_id} item={item} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Count({
  label,
  value,
  tone = "default",
}: {
  readonly label: string;
  readonly value: number;
  readonly tone?: "default" | "danger";
}) {
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <dt className="text-[13px] text-[var(--color-text-secondary)]">{label}</dt>
      <dd
        className={cn(
          "mt-1 font-display text-[2rem] font-semibold tabular-nums",
          tone === "danger" && value > 0
            ? "text-[var(--color-danger)]"
            : "text-[var(--color-text)]"
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function QueueRow({ item }: { readonly item: PlacementQueueItem }) {
  const t = useTranslations("teacher.placement");
  const tf = useTranslations("teacher.placement.flag");
  const flags = sortFlags(item.review_flags);
  const blocked = hasBlockingFlag(item.review_flags);

  return (
    <li className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--color-border)] px-5 py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-medium text-[var(--color-text)]">
          {item.student_name ?? item.student_email ?? t("unknownStudent")}
        </p>
        <p className="mt-0.5 text-[13px] text-[var(--color-text-secondary)]">
          {t("rowSummary", {
            form: item.form_code,
            attempt: item.attempt_number,
            course: item.provisional_course ?? t("noCourseYet"),
          })}
        </p>
        {flags.length > 0 ? (
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {flags.map((code) => {
              const severity = flagSeverity(code);
              return (
                <li
                  key={code}
                  className={cn(
                    "rounded-[var(--radius-pill)] px-2 py-0.5 text-[12px]",
                    severity === "blocking"
                      ? "bg-[var(--color-danger)]/12 text-[var(--color-danger)]"
                      : severity === "review"
                        ? "bg-[var(--color-warning)]/14 text-[var(--color-warning-strong,var(--color-text))]"
                        : "bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]"
                  )}
                >
                  {tf(code)}
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>

      <Link
        href={`/teacher/placement/${item.attempt_id}`}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[var(--radius-md)] border px-4 text-[14px] font-medium",
          "h-11 pointer-coarse:min-h-11 outline-none transition-colors duration-150",
          "focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40",
          blocked
            ? "border-[var(--color-danger)]/40 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/8"
            : "border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
        )}
      >
        {t("open")}
        <ArrowRight aria-hidden="true" className="size-3.5" />
      </Link>
    </li>
  );
}
