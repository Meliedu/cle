"use client";

import { useTranslations } from "next-intl";
import { FolderPlus, Upload, LinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/patterns";

interface NoMaterialsEmptyProps {
  readonly onUpload: () => void;
  readonly onAddLink: () => void;
}

/**
 * T059 — no-materials-published state. Shown when a course has no files in any
 * session folder or the unassigned bucket. A designed EmptyState (never a blank
 * div) that explains why the library is empty and offers the two ingest paths
 * inline: upload your first material, or add a link.
 */
export function NoMaterialsEmpty({ onUpload, onAddLink }: NoMaterialsEmptyProps) {
  const t = useTranslations("teacher.materials.empty");

  return (
    <EmptyState
      icon={FolderPlus}
      title={t("title")}
      reason={t("reason")}
      action={
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button size="sm" onClick={onUpload} data-icon="inline-start">
            <Upload aria-hidden="true" />
            {t("upload")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onAddLink}
            data-icon="inline-start"
          >
            <LinkIcon aria-hidden="true" />
            {t("addLink")}
          </Button>
        </div>
      }
    />
  );
}
