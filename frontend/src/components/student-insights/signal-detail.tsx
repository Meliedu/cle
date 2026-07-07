"use client";

import { useTranslations } from "next-intl";
import { FileSearch } from "lucide-react";

import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { useSignal, useEvidenceSource } from "@/hooks/use-insights";

interface SignalDetailProps {
  /** The `learning_note` id the signal reshapes; `null` renders nothing. */
  readonly signalId: string | null;
}

/** Locale date, e.g. "10 Jul 2026". */
function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Humanize a raw `source_kind` token (e.g. "quiz_attempt" → "Quiz attempt"). */
function humanizeKind(kind: string): string {
  const spaced = kind.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * S063 — the "where did this come from" provenance drawer over a single signal
 * (`learning_note`). Pure read: `useSignal` resolves the note, `useEvidenceSource`
 * traces its first cited `learning_event`. A still-unreviewed own note collapses
 * to the designed waiting state (S071) — the student never sees an AI draft's
 * content (Core §0.2). Complementary to the follow-up detail's inline reviewed
 * fields: this panel surfaces the CONTEXT ANCHOR + the raw source signal.
 */
export function SignalDetail({ signalId }: SignalDetailProps) {
  const t = useTranslations("student.followUp.signal");
  const { data: signal, isLoading, isError } = useSignal(signalId);
  const firstEventId = signal?.source_event_ids?.[0] ?? null;
  const reveal = Boolean(signal) && !signal?.waiting_for_review;
  const { data: source } = useEvidenceSource(reveal ? firstEventId : null);

  if (!signalId) return null;

  if (isLoading) {
    return <Skeleton className="h-24 w-full rounded-[var(--radius-lg)]" />;
  }

  if (isError || !signal) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  if (signal.waiting_for_review) {
    return (
      <StateBanner
        tone="waiting"
        title={t("waiting.title")}
        reason={t("waiting.reason")}
      />
    );
  }

  return (
    <section
      aria-label={t("title")}
      className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4"
    >
      <div className="flex items-center gap-2 text-[var(--color-text-secondary)]">
        <FileSearch aria-hidden="true" strokeWidth={1.85} className="size-4" />
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("title")}
        </h3>
      </div>

      {signal.context_anchor ? (
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("anchor", { anchor: signal.context_anchor })}
        </p>
      ) : null}

      {source ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-[13px]">
          <dt className="text-[var(--color-text-muted)]">{t("sourceKind")}</dt>
          <dd className="font-medium text-[var(--color-text)]">
            {humanizeKind(source.source_kind)}
          </dd>
          <dt className="text-[var(--color-text-muted)]">{t("occurredAt")}</dt>
          <dd className="tabular-nums text-[var(--color-text)]">
            {formatDate(source.occurred_at)}
          </dd>
        </dl>
      ) : (
        <p className="text-[13px] text-[var(--color-text-muted)]">
          {t("noSource")}
        </p>
      )}
    </section>
  );
}
