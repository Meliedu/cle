"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ArrowRightCircle, Info, PackageOpen } from "lucide-react";

import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import {
  useImportMemory,
  useNextTermSuggestions,
  type NextTermSuggestion,
} from "@/hooks/use-memory";
import { sourceLabel, summaryText } from "@/components/memory/memory-format";

interface StepMemoryImportProps {
  /** Course being set up — the import target. */
  readonly courseId: string;
  /** Fired when the teacher dismisses the (optional, non-blocking) step. */
  readonly onSkip?: () => void;
}

/** Suggestion text preview — first populated summary, else the instructor note. */
function previewText(item: NextTermSuggestion): string | null {
  return (
    summaryText(item.outcome_summary) ??
    summaryText(item.action_summary) ??
    summaryText(item.relationship_summary) ??
    item.instructor_comment
  );
}

interface SourceGroup {
  readonly courseId: string;
  readonly code: string | null;
  readonly name: string;
  readonly items: readonly NextTermSuggestion[];
}

function groupBySource(
  suggestions: readonly NextTermSuggestion[]
): readonly SourceGroup[] {
  const order: string[] = [];
  const map = new Map<string, NextTermSuggestion[]>();
  for (const item of suggestions) {
    const key = item.source_course_id;
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)!.push(item);
  }
  return order.map((key) => {
    const grouped = map.get(key)!;
    return {
      courseId: key,
      code: grouped[0].source_course_code,
      name: grouped[0].source_course_name,
      items: grouped,
    };
  });
}

/**
 * T023 — previous-term memory import. The real prior-term carry-forward picker
 * (unstubs the P1 placeholder). Lists `carry_forward` items from earlier
 * offerings of this course (`useNextTermSuggestions`), lets the teacher select
 * a subset, and threads them into this course's checkpoint-generation grounding
 * (`useImportMemory`). Optional + non-blocking — it is NOT a `SETUP_STEP_KEYS`
 * entry, so it never gates publish. A backend 409 (`MEMORY_UNDECIDED`) surfaces
 * as a `StateBanner` rather than a hard failure.
 */
export function StepMemoryImport({ courseId, onSkip }: StepMemoryImportProps) {
  const t = useTranslations("teacher.setup.memoryImport");
  const suggestions = useNextTermSuggestions(courseId);
  const importMemory = useImportMemory(courseId);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [importedCount, setImportedCount] = useState<number | null>(null);

  const items = useMemo(() => suggestions.data ?? [], [suggestions.data]);
  const groups = useMemo(() => groupBySource(items), [items]);

  function toggle(id: string) {
    setImportedCount(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setImportedCount(null);
    setSelected(new Set(items.map((item) => item.id)));
  }

  function clear() {
    setImportedCount(null);
    setSelected(new Set());
  }

  function runImport() {
    importMemory.mutate(
      { item_ids: [...selected] },
      {
        onSuccess: (result) => {
          setImportedCount(result.imported_count);
          setSelected(new Set());
        },
      }
    );
  }

  const isUndecided =
    importMemory.error instanceof ApiError &&
    importMemory.error.code === "MEMORY_UNDECIDED";

  const skipButton = onSkip ? (
    <Button type="button" size="sm" variant="ghost" onClick={onSkip}>
      {t("skip")}
    </Button>
  ) : undefined;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[52ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        {skipButton}
      </div>

      {suggestions.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : suggestions.isError ? (
        <StateBanner
          tone="warning"
          title={t("loadErrorTitle")}
          reason={t("loadErrorReason")}
          action={skipButton}
        />
      ) : items.length === 0 ? (
        <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]">
          <EmptyState
            variant="empty"
            icon={PackageOpen}
            title={t("empty.title")}
            reason={t("empty.reason")}
            action={skipButton}
          />
        </div>
      ) : (
        <div className="space-y-4">
          {importedCount !== null ? (
            <StateBanner
              tone="success"
              title={t("imported", { count: importedCount })}
            />
          ) : null}

          {isUndecided ? (
            <StateBanner tone="warning" title={t("undecidedError")} />
          ) : importMemory.isError ? (
            <StateBanner tone="warning" title={t("error")} />
          ) : null}

          <div className="rounded-[var(--radius-lg)] border border-[var(--color-accent)]/30 bg-[var(--color-accent-light)] p-4">
            <p className="flex items-start gap-2 text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
              <Info
                aria-hidden="true"
                strokeWidth={1.85}
                className="mt-0.5 size-3.5 shrink-0 text-[var(--color-accent)]"
              />
              {t("recommendedBody")}
            </p>
          </div>

          <div className="space-y-4">
            {groups.map((group) => (
              <fieldset key={group.courseId} className="space-y-2">
                <legend className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {sourceLabel(group.code, group.name)}
                </legend>
                <ul className="space-y-1.5">
                  {group.items.map((item) => (
                    <li key={item.id}>
                      <SuggestionCheckbox
                        item={item}
                        checked={selected.has(item.id)}
                        onToggle={() => toggle(item.id)}
                        preview={previewText(item)}
                      />
                    </li>
                  ))}
                </ul>
              </fieldset>
            ))}
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)]/70 pt-4">
            <div className="flex items-center gap-3">
              <span className="text-[13px] text-[var(--color-text-secondary)]">
                {t("selectedCount", { count: selected.size })}
              </span>
              <button
                type="button"
                onClick={selectAll}
                className="text-[12px] font-medium text-[var(--color-primary)] hover:underline"
              >
                {t("selectAll")}
              </button>
              <button
                type="button"
                onClick={clear}
                disabled={selected.size === 0}
                className="text-[12px] font-medium text-[var(--color-text-muted)] hover:underline disabled:opacity-50"
              >
                {t("clear")}
              </button>
            </div>
            <div className="flex items-center gap-2">
              {skipButton}
              <Button
                type="button"
                size="sm"
                disabled={selected.size === 0 || importMemory.isPending}
                onClick={runImport}
              >
                <ArrowRightCircle aria-hidden="true" className="size-3.5" />
                {importMemory.isPending ? t("importing") : t("import")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface SuggestionCheckboxProps {
  readonly item: NextTermSuggestion;
  readonly checked: boolean;
  readonly onToggle: () => void;
  readonly preview: string | null;
}

function SuggestionCheckbox({
  item,
  checked,
  onToggle,
  preview,
}: SuggestionCheckboxProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-[var(--radius-lg)] border px-3.5 py-3 transition-colors duration-[var(--duration-fast)]",
        checked
          ? "border-[var(--color-primary)]/50 bg-[var(--color-primary-light)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-primary)]/30 hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="mt-0.5 size-4 shrink-0 accent-[var(--color-primary)]"
      />
      <span className="min-w-0 flex-1 text-[13px] leading-relaxed text-[var(--color-text)]">
        {preview ?? item.source_course_name}
      </span>
    </label>
  );
}
