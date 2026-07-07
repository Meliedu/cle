"use client";

import { useTranslations } from "next-intl";
import { FolderCheck, Eye, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { UploadZone } from "@/components/documents/upload-zone";

interface MaterialsUploadPanelProps {
  readonly courseId: string;
  readonly onClose: () => void;
}

/**
 * T053 — the upload surface. Reuses the existing `UploadZone` (drag-drop +
 * per-file progress, invalidates the `documents` query on success) and pairs it
 * with an "after upload" explainer so a teacher understands materials are
 * private until their session is released. Assigning an upload to a session
 * happens afterwards from the table's detail panel (F7) — the shared upload
 * endpoint does not accept a `meeting_id`, so this panel deliberately does not
 * fake an assign-on-upload control.
 */
export function MaterialsUploadPanel({
  courseId,
  onClose,
}: MaterialsUploadPanelProps) {
  const t = useTranslations("teacher.materials");

  return (
    <section
      aria-label={t("upload.title")}
      className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("upload.title")}
          </h3>
          <p className="text-[12px] text-[var(--color-text-muted)]">
            {t("upload.hint")}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={onClose}
          data-icon="inline-start"
        >
          <X aria-hidden="true" />
          {t("upload.done")}
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_16rem]">
        <UploadZone courseId={courseId} />

        <aside className="space-y-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("upload.afterTitle")}
          </p>
          <Hint
            icon={FolderCheck}
            title={t("upload.savedTitle")}
            body={t("upload.savedBody")}
          />
          <Hint
            icon={Eye}
            title={t("upload.releaseTitle")}
            body={t("upload.releaseBody")}
          />
        </aside>
      </div>
    </section>
  );
}

function Hint({
  icon: Icon,
  title,
  body,
}: {
  readonly icon: typeof FolderCheck;
  readonly title: string;
  readonly body: string;
}) {
  return (
    <div className="flex gap-2.5">
      <Icon
        aria-hidden="true"
        className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
      />
      <div className="space-y-0.5">
        <p className="text-[12px] font-medium text-[var(--color-text)]">
          {title}
        </p>
        <p className="text-[11px] leading-relaxed text-[var(--color-text-muted)]">
          {body}
        </p>
      </div>
    </div>
  );
}
