"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/patterns";
import { UploadZone } from "@/components/documents/upload-zone";
import { useDocuments, type DocumentResponse } from "@/hooks/use-documents";
import { useSetStep } from "@/hooks/use-setup";

interface StepMaterialsProps {
  readonly courseId: string;
  /** Fired after the `materials` checklist flag is set. */
  readonly onComplete?: () => void;
}

/**
 * T017 — core-materials-upload step. Reuses the existing `UploadZone` (drag &
 * drop → documents pipeline) and `useDocuments` polling; it does NOT rebuild the
 * upload/processing machinery. It renders a per-document processing list and
 * flips the `materials` checklist flag once at least one document is processed
 * (`completed`) — or when the teacher explicitly skips.
 */
export function StepMaterials({ courseId, onComplete }: StepMaterialsProps) {
  const t = useTranslations("teacher.setup.materials");
  const { data: documents, isLoading } = useDocuments(courseId);
  const setStep = useSetStep(courseId);
  const [actionError, setActionError] = useState<string | null>(null);

  const docs = useMemo(() => documents ?? [], [documents]);
  // Terminal success status is "ready" (pipeline.py; matches every other FE
  // consumer, e.g. document-selector.tsx and dashboard courses/[courseId]).
  const readyCount = docs.filter((d) => d.status === "ready").length;
  const processingCount = docs.filter(
    (d) => d.status === "pending" || d.status === "processing"
  ).length;
  const hasReady = readyCount > 0;

  // Both Continue and Skip flip `materials` done=true. `setup_checklist` is
  // boolean-only (services/setup.py), so there is no distinct "skipped" state in
  // P1; the `analyzer_review` step is the real missing-source gate before
  // publish (it flags sessions/objectives without materials), so skipping here
  // is safe.
  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "materials", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

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

        <UploadZone courseId={courseId} />

        <section aria-label={t("statusLabel")} className="space-y-3">
          {isLoading ? (
            <EmptyState variant="waiting" title={t("loading")} />
          ) : docs.length === 0 ? (
            <EmptyState
              variant="empty"
              icon={FileText}
              title={t("empty.title")}
              reason={t("empty.reason")}
            />
          ) : (
            <>
              <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
                {t("processed", { ready: readyCount, total: docs.length })}
                {processingCount > 0 ? ` · ${t("processing", { count: processingCount })}` : ""}
              </p>
              <ul className="space-y-2">
                {docs.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} t={t} />
                ))}
              </ul>
            </>
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
            disabled={!hasReady || isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
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

      <MeliIsReadingAside t={t} />
    </div>
  );
}

interface DocumentRowProps {
  readonly doc: DocumentResponse;
  readonly t: ReturnType<typeof useTranslations>;
}

function DocumentRow({ doc, t }: DocumentRowProps) {
  const isProcessing = doc.status === "pending" || doc.status === "processing";
  const isFailed = doc.status === "failed";

  return (
    <li className="flex items-center gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
      <FileText
        aria-hidden="true"
        className={
          isFailed
            ? "size-5 shrink-0 text-[var(--color-error)]"
            : "size-5 shrink-0 text-[var(--color-primary)]"
        }
      />
      <p className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text)]">
        {doc.filename}
      </p>
      {isProcessing ? (
        <span className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-primary-hover)]">
          <Loader2 aria-hidden="true" className="size-3.5 animate-spin" />
          {t("state.processing")}
        </span>
      ) : isFailed ? (
        <span className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-error)]">
          <AlertCircle aria-hidden="true" className="size-3.5" />
          {t("state.failed")}
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-success)]">
          <CheckCircle2 aria-hidden="true" className="size-3.5" />
          {t("state.ready")}
        </span>
      )}
    </li>
  );
}

function MeliIsReadingAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const items = [
    { icon: FileText, key: "schedule" },
    { icon: Search, key: "outcomes" },
    { icon: Sparkles, key: "topics" },
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
