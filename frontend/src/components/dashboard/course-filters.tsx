"use client";

import { KeyRound, Plus, Search, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";

interface LanguageFacet {
  readonly value: string;
  readonly label: string;
  readonly flag: string;
  readonly count: number;
}

interface CourseFiltersProps {
  readonly totalCount: number;
  readonly filteredCount: number;
  readonly languages: readonly LanguageFacet[];
  readonly activeLanguage: string | null;
  readonly onLanguageChange: (language: string | null) => void;
  readonly query: string;
  readonly onQueryChange: (query: string) => void;
  readonly isInstructor: boolean;
  readonly onCreate: () => void;
  readonly onJoin: () => void;
}

export function CourseFilters({
  totalCount,
  filteredCount,
  languages,
  activeLanguage,
  onLanguageChange,
  query,
  onQueryChange,
  isInstructor,
  onCreate,
  onJoin,
}: CourseFiltersProps) {
  const showCount = filteredCount !== totalCount;

  return (
    <div className="space-y-5">
      {/* Title row */}
      <div className="flex items-end justify-between gap-4">
        <div className="flex items-end gap-3">
          <h1 className="text-[clamp(1.75rem,1.1rem+1.8vw,2.25rem)] font-semibold leading-[1.1] tracking-tight text-[var(--color-text)]">
            Courses
          </h1>
          <span className="pb-2 text-sm text-[var(--color-text-muted)] tabular-nums">
            {showCount
              ? `${filteredCount} of ${totalCount}`
              : totalCount === 1
                ? "1 course"
                : `${totalCount} courses`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <SearchField query={query} onChange={onQueryChange} />
          <button
            type="button"
            onClick={isInstructor ? onCreate : onJoin}
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] bg-[var(--color-text)] px-3.5 py-2 text-xs font-semibold text-[var(--color-surface)] shadow-[var(--shadow-sm)] transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-text-secondary)]"
          >
            {isInstructor ? (
              <>
                <Plus className="size-3.5" strokeWidth={2.5} />
                New
              </>
            ) : (
              <>
                <KeyRound className="size-3.5" strokeWidth={2.5} />
                Join
              </>
            )}
          </button>
        </div>
      </div>

      {/* Language facets — only render when there's something to filter by */}
      {languages.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2">
          <LanguageChip
            label="All"
            flag="∞"
            count={totalCount}
            active={activeLanguage === null}
            onClick={() => onLanguageChange(null)}
          />
          {languages.map((lang) => (
            <LanguageChip
              key={lang.value}
              label={lang.label}
              flag={lang.flag}
              count={lang.count}
              active={activeLanguage === lang.value}
              onClick={() =>
                onLanguageChange(
                  activeLanguage === lang.value ? null : lang.value
                )
              }
            />
          ))}

          <button
            type="button"
            aria-label="More filters"
            className="ml-auto inline-flex size-9 items-center justify-center rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] transition-colors duration-[var(--duration-fast)] hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)]"
          >
            <SlidersHorizontal className="size-4" strokeWidth={1.75} />
          </button>
        </div>
      ) : null}
    </div>
  );
}

function SearchField({
  query,
  onChange,
}: {
  query: string;
  onChange: (q: string) => void;
}) {
  return (
    <label className="group relative hidden items-center sm:flex">
      <Search className="pointer-events-none absolute left-3 size-4 text-[var(--color-text-muted)]" />
      <input
        type="search"
        value={query}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search courses"
        className="w-[180px] rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)] py-2 pl-9 pr-3 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] transition-all duration-[var(--duration-fast)] focus:w-[220px] focus:border-[var(--color-border-hover)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
      />
    </label>
  );
}

interface LanguageChipProps {
  readonly label: string;
  readonly flag: string;
  readonly count: number;
  readonly active: boolean;
  readonly onClick: () => void;
}

function LanguageChip({
  label,
  flag,
  count,
  active,
  onClick,
}: LanguageChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-2 rounded-[var(--radius-pill)] border px-3 py-1.5 text-xs font-medium transition-all duration-[var(--duration-fast)]",
        active
          ? "border-[var(--color-text)] bg-[var(--color-text)] text-[var(--color-surface)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)]"
      )}
    >
      <span
        className="inline-flex size-5 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-[13px] leading-none"
        aria-hidden="true"
        style={active ? { backgroundColor: "oklch(100% 0 0 / 0.15)" } : undefined}
      >
        {flag}
      </span>
      <span>{label}</span>
      <span
        className={cn(
          "tabular-nums text-[10px]",
          active
            ? "text-[var(--color-surface)]/70"
            : "text-[var(--color-text-muted)]"
        )}
      >
        {count}
      </span>
    </button>
  );
}
