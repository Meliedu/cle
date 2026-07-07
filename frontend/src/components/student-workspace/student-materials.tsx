"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { FileText, FolderOpen } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { StatusChip, releaseTone } from "@/components/course/session-status";
import type { ReleaseState } from "@/hooks/use-meetings";
import {
  useMaterials,
  type DocumentResponse,
  type MaterialsSessionGroup,
} from "@/hooks/use-documents";

import { MaterialReader } from "./material-reader";

interface StudentMaterialsProps {
  readonly courseId: string;
}

/**
 * S029 — student materials list. Documents grouped into session folders (from
 * `useMaterials`, students see only released/completed sessions) with an
 * "other materials" bucket for anything unassigned. Opening a document launches
 * the S030 reader over a signed preview URL. An empty library gets the designed
 * S032 no-materials state, never a blank panel.
 */
export function StudentMaterials({ courseId }: StudentMaterialsProps) {
  const t = useTranslations("student.materials");
  const { data, isLoading, isError } = useMaterials(courseId);
  const [selected, setSelected] = useState<DocumentResponse | null>(null);

  const sessions = useMemo<readonly MaterialsSessionGroup[]>(
    () =>
      data
        ? [...data.sessions].sort((a, b) => a.meeting_index - b.meeting_index)
        : [],
    [data]
  );
  const unassigned = data?.unassigned ?? [];

  const totalDocs =
    sessions.reduce((sum, s) => sum + s.documents.length, 0) +
    unassigned.length;

  if (isError) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (totalDocs === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title={t("empty.title")}
        reason={t("empty.reason")}
      />
    );
  }

  return (
    <section className="space-y-5">
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      {sessions.map((group) => (
        <MaterialFolder
          key={group.meeting_id}
          title={group.title || t("sessionFolder", { index: group.meeting_index })}
          releaseState={group.release_state as ReleaseState}
          releaseLabel={t(`release.${group.release_state}`)}
          docs={group.documents}
          onOpen={setSelected}
        />
      ))}

      {unassigned.length > 0 ? (
        <MaterialFolder
          title={t("unassigned")}
          docs={unassigned}
          onOpen={setSelected}
        />
      ) : null}

      <MaterialReader
        courseId={courseId}
        doc={selected}
        onClose={() => setSelected(null)}
      />
    </section>
  );
}

interface MaterialFolderProps {
  readonly title: string;
  readonly releaseState?: ReleaseState;
  readonly releaseLabel?: string;
  readonly docs: readonly DocumentResponse[];
  readonly onOpen: (doc: DocumentResponse) => void;
}

function MaterialFolder({
  title,
  releaseState,
  releaseLabel,
  docs,
  onOpen,
}: MaterialFolderProps) {
  const t = useTranslations("student.materials");
  return (
    <div className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex items-center gap-2.5 border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] px-4 py-3">
        <FolderOpen
          aria-hidden="true"
          strokeWidth={1.85}
          className="size-4 text-[var(--color-text-muted)]"
        />
        <span className="flex-1 truncate text-[13px] font-semibold text-[var(--color-text)]">
          {title}
        </span>
        {releaseState && releaseLabel ? (
          <StatusChip tone={releaseTone(releaseState)} label={releaseLabel} />
        ) : null}
      </div>

      {docs.length === 0 ? (
        <p className="px-4 py-4 text-[13px] text-[var(--color-text-muted)]">
          {t("folderEmpty")}
        </p>
      ) : (
        <ul className="divide-y divide-[var(--color-border)]">
          {docs.map((doc) => (
            <li key={doc.id}>
              <button
                type="button"
                onClick={() => onOpen(doc)}
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
              >
                <FileText
                  aria-hidden="true"
                  strokeWidth={1.85}
                  className="size-4 shrink-0 text-[var(--color-text-muted)]"
                />
                <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--color-text)]">
                  {doc.filename}
                </span>
                <span className="shrink-0 text-[12px] font-medium text-[var(--color-primary)]">
                  {t("open")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
