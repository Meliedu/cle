"use client";

import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";

/**
 * Renders the report claim-limits disclaimer VERBATIM (Core §0.2 — the pilot's
 * exact student-facing wording, never paraphrased). The report carries its own
 * `body.claim_limits` snapshot taken when it was drafted; we prefer that so the
 * text a student reads matches the report they were sent, and fall back to the
 * live pilot config (`claim_limits.report`) only when the snapshot is absent.
 * The surrounding label is the only translated chrome — the disclaimer body is
 * passed through untouched.
 */
interface ClaimLimitsNoteProps {
  /** The report's own snapshot (`body.claim_limits`). Preferred source. */
  readonly text: string | null | undefined;
  /** Live pilot fallback (`usePilotConfig().config?.claim_limits.report`). */
  readonly fallback: string | null | undefined;
}

export function ClaimLimitsNote({ text, fallback }: ClaimLimitsNoteProps) {
  const t = useTranslations("student.reports");
  const disclaimer = (text ?? "").trim() || (fallback ?? "").trim();

  // Never invent a disclaimer — if neither source has one, render nothing
  // rather than a fabricated reassurance.
  if (!disclaimer) return null;

  return (
    <aside
      aria-label={t("claimLimits.label")}
      className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-4 py-3"
    >
      <ShieldCheck
        aria-hidden="true"
        strokeWidth={1.85}
        className="mt-0.5 size-[18px] shrink-0 text-[var(--color-text-muted)]"
      />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("claimLimits.label")}
        </p>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {disclaimer}
        </p>
      </div>
    </aside>
  );
}
