"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { FileText, ListChecks, Loader2, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState, StateBanner } from "@/components/patterns";
import { SyllabusUploadCard } from "@/components/documents/syllabus-upload-card";
import {
  useApplySyllabusImport,
  useSyllabusImports,
  type SyllabusImport,
} from "@/hooks/use-syllabus";
import { useSetStep } from "@/hooks/use-setup";

interface StepSyllabusProps {
  readonly courseId: string;
  /** Fired after the `syllabus` checklist flag is set. */
  readonly onComplete?: () => void;
}

/** Top-level `parsed_payload` collections we surface as a parse summary. */
const PREVIEW_KEYS = ["modules", "meetings", "objectives", "assignments"] as const;

function previewCounts(payload: Record<string, unknown>): { key: string; count: number }[] {
  return PREVIEW_KEYS.map((key) => ({
    key,
    count: Array.isArray(payload[key]) ? (payload[key] as unknown[]).length : 0,
  })).filter((entry) => entry.count > 0);
}

/**
 * T016 — syllabus-upload step. Reuses the existing `SyllabusUploadCard` (upload
 * + trigger parse) and the `syllabus_imports` pipeline; it does NOT rebuild the
 * upload/parse machinery. The step polls the imports list, lets the teacher
 * apply a parsed import (writing curriculum into the course), and flips the
 * `syllabus` checklist flag once an import is applied — or when the teacher
 * explicitly skips.
 */
export function StepSyllabus({ courseId, onComplete }: StepSyllabusProps) {
  const t = useTranslations("teacher.setup.syllabus");
  const { data: imports, isLoading } = useSyllabusImports(courseId, { poll: true });
  const applyImport = useApplySyllabusImport(courseId);
  const setStep = useSetStep(courseId);
  const [actionError, setActionError] = useState<string | null>(null);

  const latest = imports?.[0];
  const hasApplied = useMemo(
    () => (imports ?? []).some((imp) => imp.status === "applied"),
    [imports]
  );

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "syllabus", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const handleApply = useCallback(
    async (imp: SyllabusImport) => {
      setActionError(null);
      try {
        await applyImport.mutateAsync(imp);
      } catch {
        setActionError(t("applyError"));
      }
    },
    [applyImport, t]
  );

  const isApplying = applyImport.isPending;
  const isFlipping = setStep.isPending;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        <SyllabusUploadCard courseId={courseId} />

        <section aria-label={t("statusLabel")} className="space-y-3">
          {isLoading ? (
            <EmptyState variant="waiting" title={t("loading")} />
          ) : !latest ? (
            <EmptyState
              variant="empty"
              icon={FileText}
              title={t("empty.title")}
              reason={t("empty.reason")}
            />
          ) : (
            <ImportStatus
              imp={latest}
              counts={previewCounts(latest.parsed_payload)}
              onApply={handleApply}
              isApplying={isApplying}
              t={t}
            />
          )}
        </section>

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={!hasApplied || isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 className="animate-spin" /> : null}
            {t("continue")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="lg"
            disabled={isFlipping}
            onClick={() => void flipDone()}
          >
            {t("skip")}
          </Button>
        </div>
      </div>

      <UsedDuringSetupAside t={t} />
    </div>
  );
}

interface ImportStatusProps {
  readonly imp: SyllabusImport;
  readonly counts: { key: string; count: number }[];
  readonly onApply: (imp: SyllabusImport) => void;
  readonly isApplying: boolean;
  readonly t: ReturnType<typeof useTranslations>;
}

function ImportStatus({ imp, counts, onApply, isApplying, t }: ImportStatusProps) {
  if (imp.status === "pending" || imp.status === "applying") {
    return (
      <StateBanner
        tone="waiting"
        title={t("status.parsing.title")}
        reason={t("status.parsing.reason")}
      />
    );
  }

  if (imp.status === "failed") {
    return (
      <StateBanner
        tone="warning"
        title={t("status.failed.title")}
        reason={imp.error_message ?? t("status.failed.reason")}
      />
    );
  }

  if (imp.status === "applied") {
    return (
      <StateBanner
        tone="success"
        title={t("status.applied.title")}
        reason={t("status.applied.reason")}
      />
    );
  }

  // status === "parsed" (or a superseded remnant) — offer apply.
  return (
    <div className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-start gap-3">
        <ListChecks
          aria-hidden="true"
          strokeWidth={1.85}
          className="mt-0.5 size-[18px] shrink-0 text-[var(--color-primary-hover)]"
        />
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="text-[14px] font-semibold leading-snug tracking-tight text-[var(--color-text)]">
            {t("status.parsed.title")}
          </p>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("status.parsed.reason")}
          </p>
        </div>
      </div>

      {counts.length > 0 ? (
        <ul className="flex flex-wrap gap-2">
          {counts.map((entry) => (
            <li
              key={entry.key}
              className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-2.5 py-1 text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t(`preview.${entry.key}`, { count: entry.count })}
            </li>
          ))}
        </ul>
      ) : null}

      <Button
        type="button"
        size="sm"
        disabled={isApplying}
        onClick={() => onApply(imp)}
      >
        {isApplying ? <Loader2 className="animate-spin" /> : null}
        {t("status.parsed.apply")}
      </Button>
    </div>
  );
}

function UsedDuringSetupAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const items = [
    { icon: FileText, key: "description" },
    { icon: ListChecks, key: "sessions" },
    { icon: Sparkles, key: "checkpoints" },
  ] as const;

  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <ul className="mt-4 space-y-4">
        {items.map(({ icon: Icon, key }) => (
          <li key={key} className="flex gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
              <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
            </span>
            <div className="min-w-0 space-y-0.5">
              <p className="text-[13px] font-medium text-[var(--color-text)]">
                {t(`aside.${key}.title`)}
              </p>
              <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
                {t(`aside.${key}.description`)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
