"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { RosterRow } from "@/lib/course-roster";
import type { CourseLifecycle } from "@/lib/contracts/state";

interface RosterRowItemProps {
  readonly row: RosterRow;
  /** The soonest row gets the emphasised treatment: it is next to teach. */
  readonly featured: boolean;
  /** Query string to carry into the course so Back restores the filters. */
  readonly returnSearch: string;
}

const STATUS_TONE: Record<CourseLifecycle, string> = {
  published:
    "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]",
  setup:
    "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-text)]",
  draft:
    "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]",
  archived:
    "border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-muted)]",
};

/**
 * One roster row.
 *
 * Structure follows Plate 02 rule 2: lifecycle, next session, venue, and the
 * correct verb are all present, and the verb is derived from lifecycle rather
 * than hardcoded per row. Rule 3 governs the density: this is a list row, not
 * a card, so it keeps a stable height whether or not a next class exists.
 *
 * The featured row (soonest class) gets a honey surface and the only filled
 * button in the list; every other row uses a text action.
 */
export function RosterRowItem({
  row,
  featured,
  returnSearch,
}: RosterRowItemProps) {
  const t = useTranslations("teacher.roster");
  const locale = useLocale();

  const { course, lifecycle, verb, nextClass } = row;
  const href = destinationFor(row, returnSearch);
  const label = course.code ?? course.name;

  const meta = [course.semester, "CLE", titleCase(course.language)]
    .filter((value): value is string => Boolean(value))
    .join(" · ");

  return (
    <li
      className={cn(
        "relative",
        featured
          ? "rounded-[var(--radius-xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)]"
          : "border-b border-[var(--color-border)]"
      )}
    >
      <div className="flex flex-col gap-4 px-4 py-4 md:flex-row md:items-center md:gap-6 md:px-5">
        {/* Identity */}
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <span
            aria-hidden="true"
            className={cn(
              "flex size-12 shrink-0 items-center justify-center rounded-[var(--radius-md)] text-[15px] font-semibold tracking-tight",
              featured
                ? "bg-[var(--color-sand)] text-[var(--color-text)]"
                : "bg-[var(--color-bg)] text-[var(--color-text-secondary)]"
            )}
          >
            {initials(label)}
          </span>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <p className="text-[17px] font-semibold tracking-tight text-[var(--color-text)]">
                {label}
              </p>
              <span
                className={cn(
                  "inline-flex h-6 items-center rounded-[var(--radius-pill)] border px-2.5 text-[12px] font-medium",
                  STATUS_TONE[lifecycle]
                )}
              >
                {t(`status.${lifecycle}`)}
              </span>
            </div>
            {course.code ? (
              <p className="mt-0.5 truncate text-[15px] text-[var(--color-text-secondary)]">
                {course.name}
              </p>
            ) : null}
            {meta ? (
              <p className="mt-0.5 truncate text-[13px] text-[var(--color-text-muted)]">
                {meta}
              </p>
            ) : null}
          </div>
        </div>

        {/* Operational readiness: what and when, as text */}
        <div className="min-w-0 md:w-[300px] md:shrink-0">
          <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            {featured ? t("nextToTeach") : t("nextSession")}
          </p>
          {nextClass ? (
            <>
              <p className="mt-1 truncate text-[15px] font-medium text-[var(--color-text)]">
                {nextClass.title}
              </p>
              <p className="mt-0.5 truncate text-[13px] text-[var(--color-text-secondary)]">
                {[
                  new Date(nextClass.at).toLocaleDateString(locale, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                  }),
                  new Date(nextClass.at).toLocaleTimeString(locale, {
                    hour: "2-digit",
                    minute: "2-digit",
                  }),
                  nextClass.location ?? t("online"),
                ].join(" · ")}
              </p>
            </>
          ) : (
            <p className="mt-1 text-[15px] text-[var(--color-text-muted)]">
              {lifecycle === "archived" ? t("noUpcoming") : t("notScheduled")}
            </p>
          )}
        </div>

        {/* The verb. Filled only on the featured row. */}
        <div className="shrink-0 md:w-[168px] md:text-right">
          {/*
            The visible label is the bare verb, but several rows share it
            ("Open course" on every published course). The accessible name
            qualifies it with the course so a rotor / links-list read is
            unambiguous, which linear reading gets for free from the row.
          */}
          {featured ? (
            <Button
              size="xl"
              render={<Link href={href} aria-label={`${t(`verb.${verb}`)}: ${label}`} />}
            >
              {t(`verb.${verb}`)}
            </Button>
          ) : (
            <Link
              href={href}
              aria-label={`${t(`verb.${verb}`)}: ${label}`}
              className="inline-flex h-11 items-center rounded-[var(--radius-md)] px-2 text-[14px] font-medium text-[var(--color-primary-text)] underline-offset-4 outline-none transition-colors hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
            >
              {t(`verb.${verb}`)}
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

/**
 * Where the verb goes.
 *
 * A course still in setup opens its setup flow; anything else opens the course
 * overview. Setup is transient, so it is only ever reachable from a course that
 * is genuinely incomplete, never as a standing destination.
 *
 * The current filter query rides along as `from`, so Back out of the course
 * restores the roster the teacher was looking at.
 */
function destinationFor(row: RosterRow, returnSearch: string): string {
  const base =
    row.verb === "continueSetup"
      ? `/teacher/courses/${row.course.id}/setup`
      : `/teacher/courses/${row.course.id}`;
  return returnSearch ? `${base}?from=${encodeURIComponent(returnSearch)}` : base;
}

/** Two-letter tile from a course code or name. */
function initials(label: string): string {
  const letters = label.replace(/[^A-Za-z一-鿿]/g, "");
  return (letters.slice(0, 2) || label.slice(0, 2)).toUpperCase();
}

function titleCase(input: string): string {
  return input
    .trim()
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}
