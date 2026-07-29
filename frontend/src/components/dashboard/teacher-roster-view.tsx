"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourses } from "@/hooks/use-courses";
import { useUrlState } from "@/hooks/use-url-state";
import { useCourseNextClasses } from "@/hooks/use-teaching-day";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";
import { RosterRowItem } from "@/components/dashboard/roster-row";
import {
  buildRoster,
  filterRoster,
  hasActiveFilters,
  statusOptions,
  termOptions,
  type RosterFilters,
} from "@/lib/course-roster";

/** The URL keys this surface owns. */
const FILTER_KEYS = ["q", "term", "status"] as const;

/**
 * The operational teaching roster (Plate 02).
 *
 * Three changes from the previous card grid:
 *   1. Search, term, and lifecycle sit in ONE bounded control row, and all
 *      three live in the URL so they survive entering a course and coming back.
 *   2. Rows are ordered by next class and carry lifecycle, next session, venue,
 *      and a verb that changes with status.
 *   3. Rows are list rows at a stable density, so a two-course roster does not
 *      read as unfinished and a forty-course roster does not become forty
 *      cards.
 */
export function TeacherRosterView() {
  const t = useTranslations("teacher.roster");
  const url = useUrlState();
  const { data: courses, isLoading } = useCourses();
  const [createOpen, setCreateOpen] = useState(false);

  const courseList = useMemo(() => courses ?? [], [courses]);
  const { nextClassByCourse, isLoading: scheduleLoading } =
    useCourseNextClasses();

  // Memoised on the three scalars. As a bare object literal this was a new
  // reference every render, so the filterRoster memo below never hit.
  const query = url.get("q");
  const term = url.get("term");
  const status = url.get("status");
  const filters: RosterFilters = useMemo(
    () => ({ query, term, status }),
    [query, term, status]
  );

  const rows = useMemo(
    () => buildRoster(courseList, nextClassByCourse),
    [courseList, nextClassByCourse]
  );
  const visible = useMemo(() => filterRoster(rows, filters), [rows, filters]);

  const terms = useMemo(() => termOptions(courseList), [courseList]);
  const statuses = useMemo(() => statusOptions(rows), [rows]);
  const filtersActive = hasActiveFilters(filters);

  const clearFilters = useCallback(() => {
    url.clear(FILTER_KEYS);
  }, [url]);

  if (isLoading || scheduleLoading) return <RosterSkeleton />;

  return (
    <div className="mx-auto w-full max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[30px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[34px]">
            {t("title")}
          </h1>
          <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <Button size="xl" onClick={() => setCreateOpen(true)}>
          <Plus aria-hidden="true" />
          {t("create")}
        </Button>
      </header>

      {/* One bounded control row */}
      <div className="mt-7 flex flex-wrap items-center gap-3">
        <div className="relative min-w-[240px] flex-1 sm:max-w-[380px]">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-[var(--color-text-muted)]"
          />
          <input
            type="search"
            value={filters.query}
            onChange={(event) => url.set("q", event.target.value)}
            placeholder={t("search")}
            aria-label={t("searchLabel")}
            className="h-11 w-full rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] pl-10 pr-3 text-[14px] text-[var(--color-text)] outline-none transition-colors placeholder:text-[var(--color-text-muted)] focus-visible:border-[var(--color-primary)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30 motion-reduce:transition-none"
          />
        </div>

        <FilterSelect
          label={t("termLabel")}
          value={filters.term}
          allLabel={t("allTerms")}
          options={terms.map((term) => ({ value: term, label: term }))}
          onChange={(value) => url.set("term", value)}
        />

        <FilterSelect
          label={t("statusLabel")}
          value={filters.status}
          allLabel={t("allStatus")}
          options={statuses.map((status) => ({
            value: status,
            label: t(`status.${status}`),
          }))}
          onChange={(value) => url.set("status", value)}
        />

        <p
          aria-live="polite"
          className="ml-auto text-[13px] text-[var(--color-text-muted)]"
        >
          {filtersActive
            ? t("filtered", { shown: visible.length, total: rows.length })
            : t("count", { count: rows.length })}
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyRoster onCreate={() => setCreateOpen(true)} />
      ) : visible.length === 0 ? (
        <EmptyFiltered onClear={clearFilters} />
      ) : (
        <ul className="mt-6 flex flex-col gap-px border-t border-[var(--color-border)]">
          {visible.map((row, index) => (
            <RosterRowItem
              key={row.course.id}
              row={row}
              // Only a genuinely next-to-teach course is featured: the first
              // row, and only when it actually has a class scheduled.
              featured={index === 0 && row.nextClass !== null}
              returnSearch={url.search}
            />
          ))}
        </ul>
      )}

      <CreateCourseDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

interface FilterSelectProps {
  readonly label: string;
  readonly value: string;
  readonly allLabel: string;
  readonly options: readonly { value: string; label: string }[];
  readonly onChange: (value: string) => void;
}

/**
 * A native select, deliberately. It is keyboard-accessible and screen-reader
 * correct for free, meets the 44px target at `h-11`, and needs no focus-trap
 * handling, which a custom popover on a filter row would need.
 */
function FilterSelect({
  label,
  value,
  allLabel,
  options,
  onChange,
}: FilterSelectProps) {
  if (options.length === 0) return null;

  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-11 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[14px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30 motion-reduce:transition-none"
    >
      <option value="">{allLabel}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function EmptyRoster({ onCreate }: { readonly onCreate: () => void }) {
  const t = useTranslations("teacher.roster");
  return (
    <div className="mt-8 rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border-hover)] bg-[var(--color-surface)] px-6 py-14 text-center">
      <h2 className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
        {t("empty.title")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("empty.reason")}
      </p>
      <Button size="xl" className="mt-6" onClick={onCreate}>
        <Plus aria-hidden="true" />
        {t("empty.action")}
      </Button>
    </div>
  );
}

function EmptyFiltered({ onClear }: { readonly onClear: () => void }) {
  const t = useTranslations("teacher.roster");
  return (
    <div className="mt-8 rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-12 text-center">
      <p className="text-[15px] font-semibold text-[var(--color-text)]">
        {t("emptyFiltered.title")}
      </p>
      <p className="mt-1 text-[13px] text-[var(--color-text-muted)]">
        {t("emptyFiltered.reason")}
      </p>
      <button
        type="button"
        onClick={onClear}
        className="mt-5 inline-flex h-11 items-center rounded-[var(--radius-lg)] border border-[var(--color-border)] px-4 text-[14px] font-medium text-[var(--color-text)] outline-none transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
      >
        {t("emptyFiltered.action")}
      </button>
    </div>
  );
}

function RosterSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-3">
          <Skeleton className="h-9 w-48" />
          <Skeleton className="h-4 w-72" />
        </div>
        <Skeleton className="h-11 w-36 rounded-[var(--radius-lg)]" />
      </div>
      <div className="mt-7 flex gap-3">
        <Skeleton className="h-11 w-[380px] rounded-[var(--radius-lg)]" />
        <Skeleton className="h-11 w-32 rounded-[var(--radius-lg)]" />
        <Skeleton className="h-11 w-32 rounded-[var(--radius-lg)]" />
      </div>
      <div className="mt-6 space-y-px">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-[104px]" />
        ))}
      </div>
    </div>
  );
}
