"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { ArrowRight, CalendarX2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { NextTeachingAction } from "@/lib/teaching-day";
import { describeLead } from "@/lib/teaching-day";
import type { SourceRollup } from "@/lib/contracts/state";

interface NextTeachingHeroProps {
  readonly next: NextTeachingAction | null;
  readonly sources: SourceRollup;
  readonly sourcesLoading: boolean;
}

/**
 * The dashboard's single dominant object (Plate 01, rule 1).
 *
 * "The next session is the dominant object with time, room, readiness, source
 * status, and one action." Every one of those five is present here, and there
 * is exactly one filled button on the whole dashboard: this one. Everything
 * below the hero uses text actions or quiet status, per rule 3.
 *
 * Source status is text-first: the chip and the count both say what they mean,
 * so color never carries the signal alone.
 */
export function NextTeachingHero({
  next,
  sources,
  sourcesLoading,
}: NextTeachingHeroProps) {
  const t = useTranslations("teacher.home");
  const locale = useLocale();

  if (!next) return <NoClassAhead />;

  const { entry } = next;
  const lead = describeLead(next);
  const start = new Date(entry.at);
  const timeRange = formatTimeRange(start, entry.durationMinutes, locale);

  const meta = [
    timeRange,
    entry.location,
    entry.durationMinutes
      ? t("hero.minutes", { count: entry.durationMinutes })
      : null,
  ].filter((value): value is string => Boolean(value));

  return (
    <section
      aria-labelledby="next-teaching-title"
      className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] pl-[5px]"
    >
      {/* Honey spine. Decorative: the eyebrow and heading already carry the
          meaning, so nothing depends on seeing this. */}
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[5px] bg-[var(--color-primary)]"
      />

      <div className="flex flex-col gap-6 px-6 py-6 md:px-8 md:py-7 lg:flex-row lg:items-start lg:justify-between lg:gap-10">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold tracking-tight text-[var(--color-primary-hover)]">
            {t(`lead.${lead.key}`, leadValues(lead, locale))}
          </p>

          <h2
            id="next-teaching-title"
            className="mt-2 text-[26px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[30px]"
          >
            {entry.title}
          </h2>

          <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
            {entry.courseCode} · {entry.courseName}
          </p>

          {meta.length > 0 ? (
            <dl className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-[var(--color-gold)]/35 pt-4 text-[14px] text-[var(--color-text-secondary)]">
              {meta.map((value) => (
                <dd key={value} className="font-medium">
                  {value}
                </dd>
              ))}
            </dl>
          ) : null}
        </div>

        <div className="flex shrink-0 flex-col gap-4 lg:items-end lg:text-right">
          <SourceReadinessBlock rollup={sources} isLoading={sourcesLoading} />

          <div className="flex flex-col items-start gap-2 lg:items-end">
            <Button
              size="xl"
              render={
                <Link
                  href={`/teacher/courses/${entry.courseId}/sessions`}
                />
              }
            >
              {t("hero.openSession", { title: entry.title })}
            </Button>
            <Link
              href={`/teacher/courses/${entry.courseId}`}
              className="rounded-[var(--radius-sm)] text-[13px] font-medium text-[var(--color-text-secondary)] underline-offset-4 outline-none transition-colors hover:text-[var(--color-text)] hover:underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
            >
              {t("hero.editSession")}
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

interface SourceReadinessBlockProps {
  readonly rollup: SourceRollup;
  readonly isLoading: boolean;
}

/**
 * Readiness as text first.
 *
 * The count, the chip label, and the explanatory sentence each state the same
 * fact independently, so the block survives a screenshot in greyscale and a
 * screen reader reading it linearly.
 */
function SourceReadinessBlock({ rollup, isLoading }: SourceReadinessBlockProps) {
  const t = useTranslations("teacher.home");

  if (isLoading) {
    return (
      <div className="h-14 w-40 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-sand)]/50 motion-reduce:animate-none" />
    );
  }

  const allReady = rollup.total > 0 && rollup.ready === rollup.total;
  const tone = rollup.needsAttention > 0
    ? "attention"
    : rollup.inFlight > 0
      ? "processing"
      : allReady
        ? "ready"
        : "neutral";

  const detail =
    rollup.total === 0
      ? t("hero.sourcesNone")
      : rollup.needsAttention > 0
        ? t("hero.sourcesAttention", { count: rollup.needsAttention })
        : rollup.inFlight > 0
          ? t("hero.sourcesProcessing", { count: rollup.inFlight })
          : t("hero.sourcesAllReady");

  return (
    <div className="lg:text-right">
      <p className="text-[12px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
        {t("hero.sourceReadiness")}
      </p>
      {rollup.total > 0 ? (
        <p
          className={cn(
            "mt-1 text-[24px] font-semibold tracking-tight tabular-nums",
            tone === "attention"
              ? "text-[var(--color-error)]"
              : tone === "processing"
                ? "text-[var(--color-primary-hover)]"
                : "text-[var(--color-success)]"
          )}
        >
          {t("hero.sourcesReady", {
            ready: rollup.ready,
            total: rollup.total,
          })}
        </p>
      ) : null}
      <p className="mt-0.5 max-w-[26ch] text-[13px] text-[var(--color-text-secondary)]">
        {detail}
      </p>
    </div>
  );
}

/**
 * The intentional empty state. A course with no schedule is a normal condition,
 * not a failure, so this explains what will appear here and offers the one
 * action that changes it.
 */
function NoClassAhead() {
  const t = useTranslations("teacher.home");

  return (
    <section className="rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border-hover)] bg-[var(--color-surface)] px-6 py-10 text-center md:px-8">
      <span className="mx-auto flex size-11 items-center justify-center rounded-full bg-[var(--color-bg)]">
        <CalendarX2
          aria-hidden="true"
          strokeWidth={1.6}
          className="size-5 text-[var(--color-text-muted)]"
        />
      </span>
      <h2 className="mt-4 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
        {t("empty.title")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("empty.reason")}
      </p>
      <Link
        href="/teacher/courses"
        className="mt-5 inline-flex h-11 items-center gap-1.5 rounded-[var(--radius-lg)] px-4 text-[14px] font-medium text-[var(--color-primary-hover)] outline-none transition-colors hover:bg-[var(--color-primary-light)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
      >
        {t("empty.action")}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Link>
    </section>
  );
}

/** "10:30–11:20" when a duration is known, otherwise just the start time. */
function formatTimeRange(
  start: Date,
  durationMinutes: number | null,
  locale: string
): string {
  const fmt = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
  });
  if (!durationMinutes) return fmt.format(start);
  const end = new Date(start.getTime() + durationMinutes * 60_000);
  return `${fmt.format(start)}–${fmt.format(end)}`;
}

/** Resolve the lead descriptor's raw ISO values into localised display text. */
function leadValues(
  lead: ReturnType<typeof describeLead>,
  locale: string
): Record<string, string | number> {
  const values: Record<string, string | number> = {};
  for (const [key, value] of Object.entries(lead.values)) {
    if (key === "time" && typeof value === "string") {
      values.time = new Date(value).toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
      });
    } else if (key === "at" && typeof value === "string") {
      const date = new Date(value);
      values.date = date.toLocaleDateString(locale, {
        weekday: "long",
        day: "numeric",
        month: "short",
      });
      values.time = date.toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
      });
    } else {
      values[key] = value;
    }
  }
  return values;
}
