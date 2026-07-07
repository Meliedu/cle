"use client";

import { useTranslations } from "next-intl";
import { ArrowLeft, Download, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useMaterialPreview } from "@/hooks/use-documents";
import type { DocumentResponse } from "@/hooks/use-documents";
import { materialKind } from "./material-format";

interface MaterialPreviewProps {
  readonly courseId: string;
  readonly doc: DocumentResponse;
  readonly onBack: () => void;
}

/**
 * T055 — the material reader. Fetches a short-lived signed R2 URL via
 * `useMaterialPreview` (never streams bytes through the API) and renders it in
 * an embedded viewer: PDFs in an `<iframe>`, video/audio in native players, and
 * a download-to-view card for formats browsers can't inline (docx/pptx). Errors
 * fall back to a `StateBanner` rather than a broken frame.
 */
export function MaterialPreview({
  courseId,
  doc,
  onBack,
}: MaterialPreviewProps) {
  const t = useTranslations("teacher.materials.preview");
  const { data, isLoading, isError } = useMaterialPreview(courseId, doc.id);
  const kind = materialKind(doc);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={onBack}
            data-icon="inline-start"
          >
            <ArrowLeft aria-hidden="true" />
            {t("back")}
          </Button>
          <span className="truncate text-[14px] font-semibold text-[var(--color-text)]">
            {doc.filename}
          </span>
        </div>
        {data ? (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              render={
                <a href={data.url} target="_blank" rel="noreferrer" />
              }
              data-icon="inline-start"
            >
              <ExternalLink aria-hidden="true" />
              {t("openInNewTab")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              render={<a href={data.url} download={doc.filename} />}
              data-icon="inline-start"
            >
              <Download aria-hidden="true" />
              {t("download")}
            </Button>
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <Skeleton className="h-[70vh] w-full rounded-[var(--radius-lg)]" />
      ) : isError || !data ? (
        <StateBanner
          tone="warning"
          title={t("errorTitle")}
          reason={t("errorReason")}
        />
      ) : (
        <PreviewViewer url={data.url} kind={kind} filename={doc.filename} />
      )}

      {data ? (
        <p className="text-[12px] text-[var(--color-text-muted)]">
          {t("expiresNote")}
        </p>
      ) : null}
    </section>
  );
}

interface PreviewViewerProps {
  readonly url: string;
  readonly kind: ReturnType<typeof materialKind>;
  readonly filename: string;
}

function PreviewViewer({ url, kind, filename }: PreviewViewerProps) {
  const t = useTranslations("teacher.materials.preview");

  if (kind === "pdf") {
    return (
      <iframe
        title={filename}
        src={url}
        className="h-[70vh] w-full rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]"
      />
    );
  }

  if (kind === "video") {
    return (
      <video
        controls
        src={url}
        className="max-h-[70vh] w-full rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-black"
      />
    );
  }

  if (kind === "audio") {
    return (
      <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <audio controls src={url} className="w-full" />
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <EmptyState
        title={t("inlineUnavailableTitle")}
        reason={t("inlineUnavailableReason")}
        action={
          <Button
            size="sm"
            render={<a href={url} target="_blank" rel="noreferrer" />}
            data-icon="inline-start"
          >
            <ExternalLink aria-hidden="true" />
            {t("openInNewTab")}
          </Button>
        }
      />
    </div>
  );
}
