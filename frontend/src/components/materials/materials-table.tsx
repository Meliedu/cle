"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import { StatusChip } from "@/components/course/session-status";
import type { DocumentResponse, MaterialsLibrary } from "@/hooks/use-documents";
import { ALL_FOLDER, UNASSIGNED_FOLDER } from "./materials-folder-nav";
import {
  materialKind,
  MaterialKindIcon,
  materialStatus,
  formatFileSize,
} from "./material-format";

/** A flat row: the document plus its resolved session label (or `null`). */
interface MaterialRow {
  readonly doc: DocumentResponse;
  readonly sessionIndex: number | null;
}

interface MaterialsTableProps {
  readonly library: MaterialsLibrary;
  /** Reserved folder key (`all`/`unassigned`) or a session `meeting_id`. */
  readonly folder: string;
  /** F7: currently-selected document id (row highlight). */
  readonly selectedId?: string | null;
  /** F7: select a row to drive the detail panel. Omit for a static table. */
  readonly onSelect?: (doc: DocumentResponse) => void;
}

/**
 * T052 — the materials table. Lists the documents in the active folder with
 * Name / Type / Session / Status columns. Rows become selectable in F7 (the
 * detail panel + preview/assign/remove hang off `onSelect`); until then the
 * table is a read-only inventory. Session labels resolve from the library's
 * own session grouping so no extra fetch is needed.
 */
export function MaterialsTable({
  library,
  folder,
  selectedId,
  onSelect,
}: MaterialsTableProps) {
  const t = useTranslations("teacher.materials");

  const rows = useMemo<readonly MaterialRow[]>(() => {
    const sessionRows: MaterialRow[] = library.sessions.flatMap((session) =>
      session.documents.map((doc) => ({
        doc,
        sessionIndex: session.meeting_index,
      }))
    );
    const unassignedRows: MaterialRow[] = library.unassigned.map((doc) => ({
      doc,
      sessionIndex: null,
    }));

    const all = [...sessionRows, ...unassignedRows];
    if (folder === ALL_FOLDER) return all;
    if (folder === UNASSIGNED_FOLDER) return unassignedRows;
    return all.filter((row) => row.doc.meeting_id === folder);
  }, [library, folder]);

  if (rows.length === 0) {
    return (
      <p className="rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border)] px-4 py-10 text-center text-[13px] text-[var(--color-text-muted)]">
        {t("table.empty")}
      </p>
    );
  }

  return (
    <div className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)]">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)]">
            <Th className="pl-4">{t("table.name")}</Th>
            <Th className="hidden sm:table-cell">{t("table.type")}</Th>
            <Th className="hidden md:table-cell">{t("table.session")}</Th>
            <Th className="pr-4">{t("table.status")}</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ doc, sessionIndex }) => (
            <MaterialTableRow
              key={doc.id}
              doc={doc}
              sessionIndex={sessionIndex}
              selected={doc.id === selectedId}
              onSelect={onSelect}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  className,
}: {
  readonly children: React.ReactNode;
  readonly className?: string;
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]",
        className
      )}
    >
      {children}
    </th>
  );
}

interface MaterialTableRowProps {
  readonly doc: DocumentResponse;
  readonly sessionIndex: number | null;
  readonly selected: boolean;
  readonly onSelect?: (doc: DocumentResponse) => void;
}

function MaterialTableRow({
  doc,
  sessionIndex,
  selected,
  onSelect,
}: MaterialTableRowProps) {
  const t = useTranslations("teacher.materials");
  const kind = materialKind(doc);
  const status = materialStatus(doc.status);
  const size = formatFileSize(doc.file_size);
  const interactive = Boolean(onSelect);

  return (
    <tr
      onClick={interactive ? () => onSelect?.(doc) : undefined}
      aria-selected={interactive ? selected : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={
        interactive
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect?.(doc);
              }
            }
          : undefined
      }
      className={cn(
        "border-b border-[var(--color-border)] last:border-b-0 transition-colors duration-[var(--duration-fast)]",
        interactive &&
          "cursor-pointer outline-none focus-visible:bg-[var(--color-surface-hover)] hover:bg-[var(--color-surface-hover)]",
        selected && "bg-[var(--color-primary-light)]"
      )}
    >
      <td className="py-2.5 pl-4 pr-3">
        <div className="flex items-center gap-2.5">
          <MaterialKindIcon
            kind={kind}
            className="size-4 shrink-0 text-[var(--color-primary)]"
          />
          <div className="min-w-0">
            <p className="truncate text-[13px] font-medium text-[var(--color-text)]">
              {doc.filename}
            </p>
            {size ? (
              <p className="text-[11px] text-[var(--color-text-muted)] sm:hidden">
                {t(`type.${kind}`)} · {size}
              </p>
            ) : null}
          </div>
        </div>
      </td>
      <td className="hidden px-3 py-2.5 text-[12px] text-[var(--color-text-secondary)] sm:table-cell">
        {t(`type.${kind}`)}
      </td>
      <td className="hidden px-3 py-2.5 text-[12px] md:table-cell">
        {sessionIndex != null ? (
          <span className="text-[var(--color-text-secondary)]">
            {t("folders.session", { index: sessionIndex })}
          </span>
        ) : (
          // A deliberate "no session" state, not missing data — render it as a
          // neutral chip so it doesn't read like an error next to Ready badges.
          <span className="inline-flex items-center rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-text-muted)]">
            {t("table.unassigned")}
          </span>
        )}
      </td>
      <td className="px-3 py-2.5 pr-4">
        <StatusChip tone={status.tone} label={t(`docStatus.${status.key}`)} />
      </td>
    </tr>
  );
}
