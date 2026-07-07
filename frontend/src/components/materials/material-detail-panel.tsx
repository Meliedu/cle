"use client";

import { useTranslations } from "next-intl";
import { Eye, FolderInput, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusChip } from "@/components/course/session-status";
import type { DocumentResponse } from "@/hooks/use-documents";
import {
  materialKind,
  MaterialKindIcon,
  materialStatus,
  formatFileSize,
} from "./material-format";

interface MaterialDetailPanelProps {
  readonly doc: DocumentResponse;
  readonly sessionIndex: number | null;
  readonly onPreview: () => void;
  readonly onAssign: () => void;
  readonly onRemove: () => void;
}

/**
 * T056 — the "material details" side panel (right column of the library once a
 * row is selected). Echoes the file's type / session / upload date / size and
 * exposes the three F7 actions: open the signed preview, assign it to a
 * session, and remove it. Copy-free — labels are `teacher.materials.*`.
 */
export function MaterialDetailPanel({
  doc,
  sessionIndex,
  onPreview,
  onAssign,
  onRemove,
}: MaterialDetailPanelProps) {
  const t = useTranslations("teacher.materials");
  const kind = materialKind(doc);
  const status = materialStatus(doc.status);
  const size = formatFileSize(doc.file_size);
  const uploaded = new Date(doc.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <aside
      aria-label={t("detail.title")}
      className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
    >
      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)]">
          <MaterialKindIcon
            kind={kind}
            className="size-5 text-[var(--color-primary)]"
          />
        </div>
        <div className="min-w-0 space-y-1">
          <p className="break-words text-[13px] font-semibold leading-snug text-[var(--color-text)]">
            {doc.filename}
          </p>
          <StatusChip
            tone={status.tone}
            label={t(`docStatus.${status.key}`)}
          />
        </div>
      </div>

      <dl className="space-y-2 border-y border-[var(--color-border)] py-3 text-[12px]">
        <DetailRow label={t("detail.type")}>{t(`type.${kind}`)}</DetailRow>
        <DetailRow label={t("detail.session")}>
          {sessionIndex != null
            ? t("folders.session", { index: sessionIndex })
            : t("detail.unassigned")}
        </DetailRow>
        <DetailRow label={t("detail.uploaded")}>{uploaded}</DetailRow>
        {size ? <DetailRow label={t("detail.size")}>{size}</DetailRow> : null}
      </dl>

      <div className="space-y-2">
        <Button
          size="sm"
          className="w-full justify-center"
          onClick={onPreview}
          data-icon="inline-start"
        >
          <Eye aria-hidden="true" />
          {t("detail.openPreview")}
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="w-full justify-center"
          onClick={onAssign}
          data-icon="inline-start"
        >
          <FolderInput aria-hidden="true" />
          {t("detail.assign")}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          className="w-full justify-center"
          onClick={onRemove}
          data-icon="inline-start"
        >
          <Trash2 aria-hidden="true" />
          {t("detail.remove")}
        </Button>
      </div>
    </aside>
  );
}

function DetailRow({
  label,
  children,
}: {
  readonly label: string;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-[var(--color-text-muted)]">{label}</dt>
      <dd className="truncate font-medium text-[var(--color-text)]">
        {children}
      </dd>
    </div>
  );
}
