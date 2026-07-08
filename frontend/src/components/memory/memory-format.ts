import {
  ArrowRightCircle,
  Ban,
  BookmarkCheck,
  CircleDashed,
  PencilLine,
  StickyNote,
  TrendingUp,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

import type { StateTone } from "@/components/patterns";
import type {
  MemoryDecision,
  MemoryItemResponse,
  MemoryKind,
} from "@/hooks/use-memory";

/**
 * Presentation metadata for the course-memory surfaces (F5/F6). Keeps the
 * kind/decision → icon + tone mapping in one place so the list, detail, decide
 * controls, summary, and setup importer all read consistently. Copy is NOT here
 * — labels resolve through `next-intl` (`teacher.memory.kind.*` /
 * `teacher.memory.decision.*`) so everything stays translatable.
 */

/** A decision-or-undecided discriminator used for badges/counters. */
export type DecisionSlot = MemoryDecision | "undecided";

/** Stable ordering for the kind-grouped list (outcome first — highest signal). */
export const KIND_ORDER: readonly MemoryKind[] = [
  "outcome",
  "action",
  "relationship",
  "general",
];

export const KIND_ICON: Record<MemoryKind, LucideIcon> = {
  outcome: TrendingUp,
  action: Wrench,
  relationship: Users,
  general: StickyNote,
};

/** Order the decide controls + summary counters read in. */
export const DECISION_ORDER: readonly DecisionSlot[] = [
  "carry_forward",
  "keep",
  "revise",
  "reject",
  "undecided",
];

/** Just the four real decisions (no `undecided`) — the decide-control buttons. */
export const DECISION_CHOICES: readonly MemoryDecision[] = [
  "carry_forward",
  "keep",
  "revise",
  "reject",
];

export const DECISION_ICON: Record<DecisionSlot, LucideIcon> = {
  keep: BookmarkCheck,
  revise: PencilLine,
  reject: Ban,
  carry_forward: ArrowRightCircle,
  undecided: CircleDashed,
};

/** Semantic tone (drives StateBanner/badge coloring) per decision slot. */
export const DECISION_TONE: Record<DecisionSlot, StateTone> = {
  keep: "success",
  revise: "warning",
  reject: "blocked",
  carry_forward: "info",
  undecided: "waiting",
};

/**
 * Tailwind classes for a compact decision badge — mirrors the tone palette used
 * by `StateBanner`, but sized for an inline pill.
 */
export function decisionBadgeClass(slot: DecisionSlot): string {
  switch (slot) {
    case "keep":
      return "border-[var(--color-success)]/40 bg-[var(--color-success-light)] text-[var(--color-success)]";
    case "revise":
      return "border-[var(--color-warning)]/45 bg-[var(--color-warning-light)] text-[var(--color-warning)]";
    case "reject":
      return "border-[var(--color-error)]/35 bg-[var(--color-error-light)] text-[var(--color-error)]";
    case "carry_forward":
      return "border-[var(--color-accent)]/40 bg-[var(--color-accent-light)] text-[var(--color-accent)]";
    case "undecided":
    default:
      return "border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-text-muted)]";
  }
}

/** Map a nullable stored decision to the badge/counter slot. */
export function decisionSlot(decision: MemoryDecision | null): DecisionSlot {
  return decision ?? "undecided";
}

// Free-form summary JSONBs (`relationship_summary` etc.) have no fixed schema —
// they come straight from LLM/generation output. Prefer a human-text key, then
// fall back to a compact `key: value` render so nothing is silently dropped.
const TEXT_KEYS = [
  "summary",
  "text",
  "note",
  "description",
  "detail",
  "headline",
  "title",
  "message",
] as const;

function humanizeKey(key: string): string {
  const spaced = key.replace(/[_-]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * Best-effort human string from a free-form summary JSONB. Returns `null` when
 * the summary is absent or empty so callers can show a "no summary" fallback.
 */
export function summaryText(
  summary: Record<string, unknown> | null | undefined
): string | null {
  if (!summary) return null;

  for (const key of TEXT_KEYS) {
    const value = summary[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }

  const parts = Object.entries(summary)
    .filter(
      ([, value]) =>
        value !== null &&
        value !== undefined &&
        typeof value !== "object" &&
        String(value).trim() !== ""
    )
    .map(([key, value]) => `${humanizeKey(key)}: ${String(value)}`);

  return parts.length > 0 ? parts.join(" · ") : null;
}

/** A normalized history entry for the detail timeline. */
export interface MemoryHistoryEntry {
  readonly label: string;
  readonly at: string | null;
}

const HISTORY_LABEL_KEYS = ["label", "event", "type", "action", "stage"] as const;
const HISTORY_AT_KEYS = [
  "at",
  "date",
  "timestamp",
  "recorded_at",
  "created_at",
] as const;

/**
 * Normalize a free-form `report_history` entry into `{label, at}`. Falls back to
 * a compact render for the label when no known key is present.
 */
export function historyEntry(raw: Record<string, unknown>): MemoryHistoryEntry {
  let label: string | null = null;
  for (const key of HISTORY_LABEL_KEYS) {
    const value = raw[key];
    if (typeof value === "string" && value.trim()) {
      label = humanizeKey(value.trim());
      break;
    }
  }

  let at: string | null = null;
  for (const key of HISTORY_AT_KEYS) {
    const value = raw[key];
    if (typeof value === "string" && value.trim()) {
      at = value;
      break;
    }
  }

  return { label: label ?? summaryText(raw) ?? "—", at };
}

/** Provenance label helper — "CODE · Name" or just "Name" when code is absent. */
export function sourceLabel(code: string | null, name: string): string {
  return code ? `${code} · ${name}` : name;
}

export type { MemoryItemResponse };
