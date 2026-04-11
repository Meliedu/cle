"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useRecalibrationItems,
  useToggleOverride,
  type RecalibrationItemRow,
} from "@/hooks/use-recalibration";

const CONTENT_TYPE_OPTIONS = [
  { label: "All", value: "" },
  { label: "Quiz", value: "quiz" },
  { label: "Flashcard", value: "flashcard" },
  { label: "Speaking", value: "speaking" },
] as const;

const PAGE_LIMIT = 20;

function difficultyBadgeStyle(difficulty: string | null): string {
  switch (difficulty) {
    case "easy":
      return "bg-[oklch(90%_0.05_145)] text-[var(--color-success)] border-transparent";
    case "medium":
      return "bg-[oklch(93%_0.05_75)] text-[var(--color-warning)] border-transparent";
    case "hard":
      return "bg-[oklch(90%_0.05_25)] text-[var(--color-error)] border-transparent";
    default:
      return "bg-[var(--color-surface-hover)] text-[var(--color-text-muted)] border-transparent";
  }
}

function DifficultyBadge({ difficulty }: { readonly difficulty: string | null }) {
  if (!difficulty) {
    return (
      <span className="text-xs text-[var(--color-text-muted)]">—</span>
    );
  }
  return (
    <Badge className={difficultyBadgeStyle(difficulty)}>
      {difficulty}
    </Badge>
  );
}

function ConfidenceBar({ confidence }: { readonly confidence: number | null }) {
  if (confidence === null) return <span className="text-xs text-[var(--color-text-muted)]">—</span>;
  const pct = Math.round(confidence * 100);
  const barColor =
    pct >= 70
      ? "var(--color-success)"
      : pct >= 40
      ? "var(--color-warning)"
      : "var(--color-error)";
  return (
    <div className="flex items-center gap-1.5">
      <div
        className="h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-border)]"
      >
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: barColor }}
        />
      </div>
      <span className="text-xs text-[var(--color-text-secondary)]">{pct}%</span>
    </div>
  );
}

interface ItemRowProps {
  readonly item: RecalibrationItemRow;
  readonly onToggle: (id: string) => void;
  readonly isToggling: boolean;
}

function ItemRow({ item, onToggle, isToggling }: ItemRowProps) {
  return (
    <tr className="border-b border-[var(--color-border)] last:border-0 hover:bg-[var(--color-surface-hover)] transition-colors duration-[var(--duration-fast)]">
      <td className="px-4 py-3 text-sm text-[var(--color-text-secondary)] max-w-[200px]">
        <span className="line-clamp-2">{item.item_preview}</span>
      </td>
      <td className="px-4 py-3">
        <Badge variant="outline" className="text-xs capitalize">
          {item.content_type}
        </Badge>
      </td>
      <td className="px-4 py-3">
        <DifficultyBadge difficulty={item.llm_difficulty} />
      </td>
      <td className="px-4 py-3">
        <DifficultyBadge difficulty={item.recalibrated_difficulty} />
      </td>
      <td className="px-4 py-3">
        <ConfidenceBar confidence={item.confidence} />
      </td>
      <td className="px-4 py-3 text-right text-sm text-[var(--color-text-secondary)]">
        {item.attempt_count}
      </td>
      <td className="px-4 py-3 text-right text-sm text-[var(--color-text-secondary)]">
        {Math.round(item.correct_rate * 100)}%
      </td>
      <td className="px-4 py-3">
        <Button
          size="sm"
          variant="outline"
          disabled={isToggling}
          onClick={() => onToggle(item.pool_item_id)}
          className="text-xs"
        >
          {item.instructor_override ? "Unlock" : "Reset"}
        </Button>
      </td>
    </tr>
  );
}

interface ItemTableProps {
  readonly courseId: string;
}

export function ItemTable({ courseId }: ItemTableProps) {
  const [contentType, setContentType] = useState("");
  const [page, setPage] = useState(1);

  const { data: items, isLoading } = useRecalibrationItems(courseId, {
    content_type: contentType || undefined,
    page,
    limit: PAGE_LIMIT,
  });

  const toggleOverride = useToggleOverride(courseId);

  const handleContentTypeChange = (value: string) => {
    setContentType(value);
    setPage(1);
  };

  return (
    <div className="space-y-4">
      {/* Filter buttons */}
      <div className="flex flex-wrap gap-2">
        {CONTENT_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => handleContentTypeChange(opt.value)}
            className={[
              "rounded-[var(--radius-md)] px-3 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-fast)]",
              contentType === opt.value
                ? "bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
                : "bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] hover:bg-[var(--color-border-hover)]",
            ].join(" ")}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-[var(--radius-lg)] border border-[var(--color-border)]">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)]">
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">Preview</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">Type</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">LLM Label</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">Recalibrated</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">Confidence</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-[var(--color-text-muted)]">Attempts</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-[var(--color-text-muted)]">Correct %</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-[var(--color-text-muted)]">Override</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-[var(--color-border)]">
                  {Array.from({ length: 8 }).map((__, j) => (
                    <td key={j} className="px-4 py-3">
                      <Skeleton className="h-4 w-full" />
                    </td>
                  ))}
                </tr>
              ))
            ) : !items || items.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  className="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]"
                >
                  No items found.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <ItemRow
                  key={item.pool_item_id}
                  item={item}
                  onToggle={(id) => toggleOverride.mutate(id)}
                  isToggling={toggleOverride.isPending}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          disabled={page <= 1 || isLoading}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Previous
        </Button>
        <span className="text-sm text-[var(--color-text-secondary)]">
          Page {page}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={isLoading || !items || items.length < PAGE_LIMIT}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  );
}
