"use client";

import { useTranslations } from "next-intl";
import { Folder, FolderOpen, Layers, Inbox } from "lucide-react";

import { cn } from "@/lib/utils";
import { StatusChip, releaseTone } from "@/components/course/session-status";
import type { ReleaseState } from "@/hooks/use-meetings";
import type { MaterialsLibrary } from "@/hooks/use-documents";

/** Reserved folder keys; any other value is a session `meeting_id` (a UUID). */
export const ALL_FOLDER = "all";
export const UNASSIGNED_FOLDER = "unassigned";

interface MaterialsFolderNavProps {
  readonly library: MaterialsLibrary;
  readonly selected: string;
  readonly onSelect: (folder: string) => void;
}

/**
 * T054/T055 — the "auto session folders" rail. Documents are grouped by
 * `meeting_id` server-side (`useMaterials`); this lists an "All materials"
 * entry, one folder per session (carrying its `release_state` chip), and an
 * "Unassigned" bucket. Folders are read-only here — they mirror the sessions
 * created in course setup (Decision 6: folders = group-by-meeting, no new
 * join table), so this is a filter, not a CRUD surface.
 */
export function MaterialsFolderNav({
  library,
  selected,
  onSelect,
}: MaterialsFolderNavProps) {
  const t = useTranslations("teacher.materials");

  const totalCount =
    library.unassigned.length +
    library.sessions.reduce((sum, s) => sum + s.documents.length, 0);

  return (
    <nav aria-label={t("folders.title")} className="space-y-3">
      <div className="space-y-1">
        <h3 className="px-2 text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("folders.title")}
        </h3>
        <p className="px-2 text-[12px] leading-relaxed text-[var(--color-text-muted)]">
          {t("folders.note")}
        </p>
      </div>

      <ul className="space-y-0.5">
        <FolderButton
          icon={Layers}
          label={t("folders.all")}
          count={totalCount}
          active={selected === ALL_FOLDER}
          onClick={() => onSelect(ALL_FOLDER)}
        />

        {library.sessions.map((session) => (
          <FolderButton
            key={session.meeting_id}
            icon={selected === session.meeting_id ? FolderOpen : Folder}
            label={t("folders.session", { index: session.meeting_index })}
            secondary={session.title}
            count={session.documents.length}
            active={selected === session.meeting_id}
            onClick={() => onSelect(session.meeting_id)}
            chip={
              <StatusChip
                tone={releaseTone(session.release_state as ReleaseState)}
                label={t(`release.${session.release_state}`)}
              />
            }
          />
        ))}

        <FolderButton
          icon={Inbox}
          label={t("folders.unassigned")}
          count={library.unassigned.length}
          active={selected === UNASSIGNED_FOLDER}
          onClick={() => onSelect(UNASSIGNED_FOLDER)}
        />
      </ul>
    </nav>
  );
}

interface FolderButtonProps {
  readonly icon: typeof Folder;
  readonly label: string;
  readonly secondary?: string | null;
  readonly count: number;
  readonly active: boolean;
  readonly onClick: () => void;
  readonly chip?: React.ReactNode;
}

function FolderButton({
  icon: Icon,
  label,
  secondary,
  count,
  active,
  onClick,
  chip,
}: FolderButtonProps) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        aria-current={active ? "true" : undefined}
        className={cn(
          "flex w-full items-center gap-2 rounded-[var(--radius-md)] px-2 py-2 text-left transition-colors duration-[var(--duration-fast)]",
          active
            ? "bg-[var(--color-primary-light)] text-[var(--color-text)]"
            : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
        )}
      >
        <Icon
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0",
            active
              ? "text-[var(--color-primary)]"
              : "text-[var(--color-text-muted)]"
          )}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-[13px] font-medium">{label}</span>
            {chip}
          </span>
          {secondary ? (
            <span className="block truncate text-[11px] text-[var(--color-text-muted)]">
              {secondary}
            </span>
          ) : null}
        </span>
        <span className="shrink-0 rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)] px-1.5 text-[11px] font-medium tabular-nums text-[var(--color-text-muted)]">
          {count}
        </span>
      </button>
    </li>
  );
}
