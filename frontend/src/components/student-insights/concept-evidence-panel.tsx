"use client";

import { useTranslations } from "next-intl";

import type { ConceptMasteryEntry } from "@/hooks/use-insights";

interface ConceptEvidencePanelProps {
  readonly entry: ConceptMasteryEntry;
}

/** Format a 0–1 ratio as a whole-percent string, e.g. 0.72 → "72%". */
function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Locale date, e.g. "10 Jul 2026". */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * S063 (concept grain) — the "where did this come from" panel for one concept.
 * The learning-profile payload reshapes `concept_mastery` and carries NO note id
 * per concept, so this surfaces the honest per-concept evidence we DO have:
 * mastery, confidence, how many attempts fed it, and when it was last seen.
 * Never fabricates a signal the data can't support (Decision 6).
 */
export function ConceptEvidencePanel({ entry }: ConceptEvidencePanelProps) {
  const t = useTranslations("student.profile.evidence");

  return (
    <div className="space-y-3 border-t border-[var(--color-border)] px-4 py-3">
      <Meter label={t("mastery")} value={entry.mastery_score} tone="primary" />
      <Meter label={t("confidence")} value={entry.confidence} tone="accent" />

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
        <dt className="text-[var(--color-text-muted)]">{t("attempts")}</dt>
        <dd className="tabular-nums text-[var(--color-text)]">
          {entry.attempt_count}
        </dd>
        <dt className="text-[var(--color-text-muted)]">{t("lastSeen")}</dt>
        <dd className="tabular-nums text-[var(--color-text)]">
          {entry.last_attempt_at ? formatDate(entry.last_attempt_at) : t("never")}
        </dd>
      </dl>

      <p className="text-[12px] leading-relaxed text-[var(--color-text-muted)]">
        {t("note")}
      </p>
    </div>
  );
}

interface MeterProps {
  readonly label: string;
  readonly value: number;
  readonly tone: "primary" | "accent";
}

/** A labelled 0–1 progress meter with an accessible value. */
function Meter({ label, value, tone }: MeterProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const fill =
    tone === "primary"
      ? "bg-[var(--color-primary)]"
      : "bg-[var(--color-accent)]";
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[12px]">
        <span className="font-medium text-[var(--color-text-secondary)]">
          {label}
        </span>
        <span className="tabular-nums font-semibold text-[var(--color-text)]">
          {pct(clamped)}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={Math.round(clamped * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 w-full overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
      >
        <div
          className={`h-full rounded-[var(--radius-pill)] ${fill}`}
          style={{ width: `${clamped * 100}%` }}
        />
      </div>
    </div>
  );
}
