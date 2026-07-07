"use client";

import { useTranslations } from "next-intl";
import { Download, ExternalLink } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import {
  useMaterialPreview,
  type DocumentResponse,
} from "@/hooks/use-documents";

interface MaterialReaderProps {
  readonly courseId: string;
  /** The material to read, or `null` when the reader is closed. */
  readonly doc: DocumentResponse | null;
  readonly onClose: () => void;
}

/**
 * S030 — material reader. Opens a short-lived signed R2 URL
 * (`useMaterialPreview`, fetched only while the reader is open) inside an
 * embedded viewer, with an open-in-new-tab / download fallback for file types
 * the browser can't inline. A preview error (not released, not enrolled, or
 * expired) surfaces a friendly banner rather than a broken frame.
 */
export function MaterialReader({ courseId, doc, onClose }: MaterialReaderProps) {
  const t = useTranslations("student.materials.reader");
  const open = doc !== null;
  const preview = useMaterialPreview(courseId, doc?.id ?? null, open);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="flex h-[85vh] max-w-[calc(100%-2rem)] flex-col gap-4 sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="truncate">
            {doc?.filename ?? t("title")}
          </DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)]">
          {preview.isLoading ? (
            <Skeleton className="size-full" />
          ) : preview.isError || !preview.data ? (
            <div className="flex h-full items-center justify-center p-6">
              <StateBanner
                tone="blocked"
                title={t("error.title")}
                reason={t("error.reason")}
              />
            </div>
          ) : (
            <iframe
              src={preview.data.url}
              title={doc?.filename ?? t("title")}
              className="size-full border-0"
            />
          )}
        </div>

        {preview.data ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              variant="outline"
              size="sm"
              render={
                <a
                  href={preview.data.url}
                  target="_blank"
                  rel="noopener noreferrer"
                />
              }
            >
              <ExternalLink aria-hidden="true" className="size-4" />
              {t("openTab")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              render={
                <a href={preview.data.url} download={preview.data.filename} />
              }
            >
              <Download aria-hidden="true" className="size-4" />
              {t("download")}
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
