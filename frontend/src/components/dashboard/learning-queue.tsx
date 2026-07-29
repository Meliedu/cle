"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import { actionVerbKey, type LearningAction } from "@/lib/learning-path";
import { destinationFor } from "@/components/dashboard/learning-action-hero";

interface LearningQueueProps {
  readonly actions: readonly LearningAction[];
}

/**
 * Everything else on the learner's path.
 *
 * The rule this component exists to satisfy (Student 02, note 03):
 *
 *   Locked, saved, submitted, and reviewed states must survive navigation and
 *   remain understandable without color or animation.
 *
 * So a blocked row states its dependency as a sentence next to the title, and
 * a blocked row is not a link: it renders as plain content, because offering a
 * link to work that cannot be opened is a promise the destination breaks.
 */
export function LearningQueue({ actions }: LearningQueueProps) {
  const t = useTranslations("student.home");
  const locale = useLocale();

  return (
    <section aria-labelledby="learning-queue-title">
      <h2
        id="learning-queue-title"
        className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
      >
        {t("laterToday")}
      </h2>

      {actions.length === 0 ? (
        <p className="mt-3 border-t border-[var(--color-border)] pt-4 text-[14px] text-[var(--color-text-muted)]">
          {t("laterTodayEmpty")}
        </p>
      ) : (
        <ul className="mt-3 border-t border-[var(--color-border)]">
          {actions.map((action) => {
            const verb = actionVerbKey(action);
            const blocked = action.availability.state !== "available";
            const due = action.item.due_at ? new Date(action.item.due_at) : null;

            const body = (
              <>
                <span className="w-14 shrink-0 text-[14px] font-medium tabular-nums text-[var(--color-text-secondary)]">
                  {due
                    ? due.toLocaleTimeString(locale, {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "--:--"}
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-medium text-[var(--color-text)]">
                    {action.item.title}
                  </span>
                  {/*
                    The unlock reason sits inline with the title, not in a
                    tooltip: it must be readable without hover and without
                    color.
                  */}
                  <span className="mt-0.5 block truncate text-[13px] text-[var(--color-text-muted)]">
                    {[
                      action.courseCode,
                      t(`kind.${action.item.source_kind}`),
                      action.availability.reason,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>

                <span
                  className={cn(
                    "inline-flex h-6 shrink-0 items-center rounded-[var(--radius-pill)] border px-2.5 text-[12px] font-medium",
                    blocked
                      ? "border-[var(--color-accent)]/35 bg-[var(--color-accent-light)] text-[var(--color-accent-hover)]"
                      : action.work === "submitted" || action.work === "reviewed"
                        ? "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]"
                        : "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-hover)]"
                  )}
                >
                  {t(`chip.${verb}`)}
                </span>
              </>
            );

            return (
              <li
                key={action.item.id}
                className="border-b border-[var(--color-border)]"
              >
                {blocked ? (
                  <div className="flex min-h-[64px] items-center gap-4 px-2 py-3">
                    {body}
                  </div>
                ) : (
                  <Link
                    href={destinationFor(action)}
                    className="flex min-h-[64px] items-center gap-4 rounded-[var(--radius-md)] px-2 py-3 outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
                  >
                    {body}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
