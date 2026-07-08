"use client";

import { useTranslations } from "next-intl";
import { FileSearch } from "lucide-react";

import { EmptyState } from "@/components/patterns";
import { Badge } from "@/components/ui/badge";
import type { EvidenceAppendixEntry } from "@/hooks/use-reports";

interface EvidenceAppendixProps {
  readonly entries: readonly EvidenceAppendixEntry[];
}

/**
 * T084 — the report evidence appendix. Renders the reviewed-note refs the
 * backend resolved from `evidence_refs` (reviewed/edited notes only — an
 * unreviewed id is filtered out server-side, Decision 3). Each row shows the
 * observed signal, the teacher's draft interpretation, and any limitation note,
 * so the report's claims are traceable to their evidence.
 */
export function EvidenceAppendix({ entries }: EvidenceAppendixProps) {
  const t = useTranslations("teacher.reports.appendix");

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={FileSearch}
        title={t("emptyTitle")}
        reason={t("emptyReason")}
      />
    );
  }

  return (
    <ul className="space-y-3" aria-label={t("title")}>
      {entries.map((entry) => (
        <li
          key={entry.id}
          className="space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("observedSignal")}
            </span>
            <Badge variant="outline" className="h-4 px-1.5 text-[10px]">
              {entry.review_status}
            </Badge>
          </div>

          {entry.observed_signal ? (
            <p className="text-[14px] leading-relaxed text-[var(--color-text)]">
              {entry.observed_signal}
            </p>
          ) : (
            <p className="text-[13px] text-[var(--color-text-muted)]">
              {t("noSignal")}
            </p>
          )}

          {entry.draft_interpretation ? (
            <Field
              label={t("draftInterpretation")}
              value={entry.draft_interpretation}
            />
          ) : null}

          {entry.limitation_note ? (
            <Field label={t("limitationNote")} value={entry.limitation_note} />
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function Field({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {value}
      </p>
    </div>
  );
}
