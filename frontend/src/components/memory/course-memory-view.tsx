"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronRight, MousePointerClick, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, PageHeader, StateBanner } from "@/components/patterns";
import {
  useMemory,
  type MemoryItemResponse,
  type MemoryKind,
} from "@/hooks/use-memory";

import { MemoryItemDetail } from "./memory-item-detail";
import { NextTermSuggestions } from "./next-term-suggestions";
import {
  DECISION_ICON,
  KIND_ICON,
  KIND_ORDER,
  decisionBadgeClass,
  decisionSlot,
  summaryText,
} from "./memory-format";

interface CourseMemoryViewProps {
  readonly courseId: string;
}

/**
 * T086/T087 — teacher course memory workspace. Reshapes `useMemory` into a
 * kind-grouped list (outcome / action / relationship / general) paired with a
 * detail panel that carries the audited decide controls. The T080 next-term
 * suggestions read sits beneath. An evidence-free course renders the designed
 * empty state; the list auto-selects the first item so the detail is never
 * blank on desktop.
 */
export function CourseMemoryView({ courseId }: CourseMemoryViewProps) {
  const t = useTranslations("teacher.memory");
  const { data, isLoading, isError } = useMemory(courseId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const items = useMemo(() => data ?? [], [data]);

  // Auto-select the first item once loaded (desktop two-pane never blank),
  // and recover if the selected item disappears after an invalidation.
  useEffect(() => {
    if (items.length === 0) {
      if (selectedId !== null) setSelectedId(null);
      return;
    }
    const stillPresent = items.some((item) => item.id === selectedId);
    if (!stillPresent) setSelectedId(items[0].id);
  }, [items, selectedId]);

  const grouped = useMemo(() => groupByKind(items), [items]);
  const selected = items.find((item) => item.id === selectedId) ?? null;

  return (
    <div className="space-y-6">
      <PageHeader as="h2" title={t("title")} description={t("subtitle")} />

      {isLoading ? (
        <MemoryLoading />
      ) : isError ? (
        <StateBanner
          tone="warning"
          title={t("loadErrorTitle")}
          reason={t("loadErrorReason")}
        />
      ) : items.length === 0 ? (
        <>
          <EmptyState
            variant="waiting"
            title={t("empty.title")}
            reason={t("empty.reason")}
          />
          <NextTermSuggestions courseId={courseId} />
        </>
      ) : (
        <>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
            <MemoryList
              grouped={grouped}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
            <div className="min-w-0">
              {selected ? (
                <MemoryItemDetail
                  courseId={courseId}
                  item={selected}
                  onBack={() => setSelectedId(null)}
                />
              ) : (
                <EmptyState
                  variant="empty"
                  icon={MousePointerClick}
                  title={t("detail.selectTitle")}
                  reason={t("detail.selectPrompt")}
                  className="rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)]"
                />
              )}
            </div>
          </div>

          <NextTermSuggestions courseId={courseId} />
        </>
      )}
    </div>
  );
}

interface KindGroup {
  readonly kind: MemoryKind;
  readonly items: readonly MemoryItemResponse[];
}

function groupByKind(items: readonly MemoryItemResponse[]): readonly KindGroup[] {
  return KIND_ORDER.map((kind) => ({
    kind,
    items: items.filter((item) => item.kind === kind),
  })).filter((group) => group.items.length > 0);
}

interface MemoryListProps {
  readonly grouped: readonly KindGroup[];
  readonly selectedId: string | null;
  readonly onSelect: (id: string) => void;
}

function MemoryList({ grouped, selectedId, onSelect }: MemoryListProps) {
  const t = useTranslations("teacher.memory");
  const tKind = useTranslations("teacher.memory.kind");

  return (
    <div className="space-y-5">
      {grouped.map((group) => {
        const KindIcon: LucideIcon = KIND_ICON[group.kind];
        return (
          <div key={group.kind} className="space-y-2">
            <div className="flex items-center gap-2 px-1">
              <KindIcon
                aria-hidden="true"
                strokeWidth={1.85}
                className="size-3.5 text-[var(--color-text-muted)]"
              />
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                {tKind(group.kind)}
              </h3>
              <span className="text-[11px] text-[var(--color-text-muted)]">
                {t("list.count", { count: group.items.length })}
              </span>
            </div>
            <ul className="space-y-1.5">
              {group.items.map((item) => (
                <li key={item.id}>
                  <MemoryListRow
                    item={item}
                    selected={item.id === selectedId}
                    onSelect={() => onSelect(item.id)}
                  />
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

interface MemoryListRowProps {
  readonly item: MemoryItemResponse;
  readonly selected: boolean;
  readonly onSelect: () => void;
}

function MemoryListRow({ item, selected, onSelect }: MemoryListRowProps) {
  const tDecision = useTranslations("teacher.memory.decision");
  const slot = decisionSlot(item.decision);
  const DecisionIcon = DECISION_ICON[slot];
  const preview =
    summaryText(item.outcome_summary) ??
    summaryText(item.action_summary) ??
    summaryText(item.relationship_summary) ??
    item.instructor_comment ??
    tDecision(slot);

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "group flex w-full items-center gap-3 rounded-[var(--radius-lg)] border px-3.5 py-3 text-left transition-colors duration-[var(--duration-fast)]",
        selected
          ? "border-[var(--color-primary)]/50 bg-[var(--color-primary-light)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-primary)]/30 hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="truncate text-[13px] font-medium text-[var(--color-text)]">
          {preview}
        </p>
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
            decisionBadgeClass(slot)
          )}
        >
          <DecisionIcon aria-hidden="true" className="size-2.5" />
          {tDecision(slot)}
        </span>
      </div>
      <ChevronRight
        aria-hidden="true"
        className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5"
      />
    </button>
  );
}

function MemoryLoading() {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  );
}
