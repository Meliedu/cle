"use client";

import { useTranslations } from "next-intl";
import { Database, MapPin } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useEvidenceSource } from "@/hooks/use-insights";

/**
 * T078 — evidence source view. The instructor "where did this signal come from"
 * panel over `useEvidenceSource`: the raw `learning_event` a signal traces back
 * to (source kind, stage, event type, when it occurred, the context anchor, and
 * the recorded value). Pure read — reshapes an existing row, computes nothing.
 * Reused inside the T077 signal drawer and standalone. A signal with no linked
 * source event renders the designed empty state (never fabricated data).
 */

interface EvidenceSourceViewProps {
  /** The `learning_event` id to resolve, or `null` when none is linked. */
  readonly eventId: string | null;
  /** Compact variant tightens spacing for the in-drawer placement. */
  readonly compact?: boolean;
}

export function EvidenceSourceView({ eventId, compact = false }: EvidenceSourceViewProps) {
  const t = useTranslations("teacher.insights");
  const { data: source, isLoading, isError } = useEvidenceSource(eventId);

  if (eventId === null) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] p-4 text-[12px] text-[var(--color-text-muted)]">
        {t("evidence.empty")}
      </div>
    );
  }

  if (isLoading) {
    return <Skeleton className="h-28 w-full" />;
  }

  if (isError || !source) {
    return (
      <StateBanner
        tone="warning"
        title={t("evidence.loadErrorTitle")}
        reason={t("evidence.loadErrorReason")}
      />
    );
  }

  const sourceLabel = t.has(`evidence.sourceKind.${source.source_kind}`)
    ? t(`evidence.sourceKind.${source.source_kind}`)
    : source.source_kind;
  const occurred = new Date(source.occurred_at);
  const occurredLabel = Number.isNaN(occurred.getTime())
    ? source.occurred_at
    : occurred.toLocaleString();
  const valueEntries = Object.entries(source.value ?? {}).slice(0, 6);

  return (
    <div className="space-y-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-4">
      <div className="flex items-center gap-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
          <Database aria-hidden="true" strokeWidth={1.85} className="size-3.5" />
        </span>
        <div>
          <p className="text-[12px] font-semibold text-[var(--color-text)]">
            {t("evidence.title")}
          </p>
          {!compact ? (
            <p className="text-[11px] text-[var(--color-text-muted)]">
              {t("evidence.subtitle")}
            </p>
          ) : null}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[12px]">
        <Field label={t("evidence.source")}>{sourceLabel}</Field>
        <Field label={t("evidence.stage")}>{source.stage}</Field>
        <Field label={t("evidence.eventType")}>{source.event_type}</Field>
        <Field label={t("evidence.occurredAt")}>{occurredLabel}</Field>
      </dl>

      {source.context_anchor ? (
        <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-3 py-2 text-[12px]">
          <MapPin
            aria-hidden="true"
            strokeWidth={1.75}
            className="mt-0.5 size-3.5 shrink-0 text-[var(--color-text-muted)]"
          />
          <div className="min-w-0">
            <dt className="text-[var(--color-text-muted)]">
              {t("evidence.anchor")}
            </dt>
            <dd className="mt-0.5 text-[var(--color-text-secondary)]">
              {typeof source.context_anchor === "string"
                ? source.context_anchor
                : JSON.stringify(source.context_anchor)}
            </dd>
          </div>
        </div>
      ) : null}

      {valueEntries.length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("evidence.value")}
          </p>
          <dl className="space-y-1">
            {valueEntries.map(([key, val]) => (
              <div key={key} className="flex items-baseline justify-between gap-3">
                <dt className="text-[12px] text-[var(--color-text-muted)]">
                  {key}
                </dt>
                <dd className="truncate text-right text-[12px] font-medium text-[var(--color-text)]">
                  {formatValue(val)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[var(--color-text-muted)]">{label}</dt>
      <dd className="mt-0.5 truncate font-medium text-[var(--color-text)]">
        {children}
      </dd>
    </div>
  );
}

/** Render a JSON scalar readably; objects/arrays collapse to a short string. */
function formatValue(val: unknown): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "boolean") return val ? "true" : "false";
  if (typeof val === "number") return String(val);
  if (typeof val === "string") return val;
  return JSON.stringify(val);
}
