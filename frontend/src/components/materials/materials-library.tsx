"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Upload, LinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBanner } from "@/components/patterns";
import { useMaterials } from "@/hooks/use-documents";
import type { DocumentResponse, MaterialsLibrary as MaterialsLibraryData } from "@/hooks/use-documents";
import { MaterialsFolderNav, ALL_FOLDER } from "./materials-folder-nav";
import { MaterialsTable } from "./materials-table";
import { MaterialsUploadPanel } from "./materials-upload-panel";
import { MaterialDetailPanel } from "./material-detail-panel";
import { MaterialPreview } from "./material-preview";
import { AssignSessionDialog } from "./assign-session-dialog";
import { RemoveMaterialDialog } from "./remove-material-dialog";
import { NoMaterialsEmpty } from "./no-materials-empty";
import {
  LinkResourceDialog,
  type LinkSessionOption,
} from "./link-resource-dialog";

interface MaterialsLibraryProps {
  readonly courseId: string;
}

interface Notice {
  readonly tone: "info" | "warning";
  readonly title: string;
  readonly reason: string;
}

/** A resolved document plus its session index (or `null` when unassigned). */
interface MaterialEntry {
  readonly doc: DocumentResponse;
  readonly sessionIndex: number | null;
}

/** Flatten the library into an id → {doc, sessionIndex} lookup. */
function indexMaterials(
  library: MaterialsLibraryData
): ReadonlyMap<string, MaterialEntry> {
  const map = new Map<string, MaterialEntry>();
  for (const session of library.sessions) {
    for (const doc of session.documents) {
      map.set(doc.id, { doc, sessionIndex: session.meeting_index });
    }
  }
  for (const doc of library.unassigned) {
    map.set(doc.id, { doc, sessionIndex: null });
  }
  return map;
}

/**
 * T052–T059 — teacher materials library orchestrator. Composes the session-
 * folder rail, the materials table, upload panel, and add-link modal (F6), plus
 * the F7 flows: a detail side panel per selected file, a signed-URL preview
 * reader, assign-to-session, remove confirmation, and the no-materials state.
 */
export function MaterialsLibrary({ courseId }: MaterialsLibraryProps) {
  const t = useTranslations("teacher.materials");
  const { data: library, isLoading, isError } = useMaterials(courseId);

  const [folder, setFolder] = useState<string>(ALL_FOLDER);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [assignId, setAssignId] = useState<string | null>(null);
  const [removeId, setRemoveId] = useState<string | null>(null);

  const byId = useMemo(
    () => (library ? indexMaterials(library) : new Map<string, MaterialEntry>()),
    [library]
  );

  // Drop a selection whose document has vanished (e.g. after a delete).
  useEffect(() => {
    if (selectedId && !byId.has(selectedId)) setSelectedId(null);
  }, [byId, selectedId]);

  const sessionOptions = useMemo<readonly LinkSessionOption[]>(
    () =>
      (library?.sessions ?? []).map((s) => ({
        meetingId: s.meeting_id,
        index: s.meeting_index,
        title: s.title,
      })),
    [library]
  );

  const isEmpty =
    library != null &&
    library.sessions.every((s) => s.documents.length === 0) &&
    library.unassigned.length === 0;

  const selected = selectedId ? byId.get(selectedId) : undefined;
  const previewEntry = previewId ? byId.get(previewId) : undefined;
  const assignEntry = assignId ? byId.get(assignId) : undefined;
  const removeEntry = removeId ? byId.get(removeId) : undefined;

  // Full-screen reader replaces the browse surface (T055/T056).
  if (previewEntry) {
    return (
      <MaterialPreview
        courseId={courseId}
        doc={previewEntry.doc}
        onBack={() => setPreviewId(null)}
      />
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setLinkOpen(true)}
            data-icon="inline-start"
          >
            <LinkIcon aria-hidden="true" />
            {t("actions.addLink")}
          </Button>
          <Button
            size="sm"
            onClick={() => setUploadOpen((v) => !v)}
            aria-expanded={uploadOpen}
            data-icon="inline-start"
          >
            <Upload aria-hidden="true" />
            {t("actions.upload")}
          </Button>
        </div>
      </div>

      {notice ? (
        <StateBanner
          tone={notice.tone}
          title={notice.title}
          reason={notice.reason}
          action={
            <Button size="sm" variant="ghost" onClick={() => setNotice(null)}>
              {t("actions.dismiss")}
            </Button>
          }
        />
      ) : null}

      {uploadOpen ? (
        <MaterialsUploadPanel
          courseId={courseId}
          onClose={() => setUploadOpen(false)}
        />
      ) : null}

      {isLoading ? (
        <LibrarySkeleton />
      ) : isError || !library ? (
        <StateBanner
          tone="warning"
          title={t("loadError.title")}
          reason={t("loadError.reason")}
        />
      ) : isEmpty ? (
        <NoMaterialsEmpty
          onUpload={() => setUploadOpen(true)}
          onAddLink={() => setLinkOpen(true)}
        />
      ) : (
        <div
          className={
            selected
              ? "grid gap-5 lg:grid-cols-[13rem_1fr_17rem]"
              : "grid gap-5 lg:grid-cols-[14rem_1fr]"
          }
        >
          <MaterialsFolderNav
            library={library}
            selected={folder}
            onSelect={setFolder}
          />
          <MaterialsTable
            library={library}
            folder={folder}
            selectedId={selectedId}
            onSelect={(doc) => setSelectedId(doc.id)}
          />
          {selected ? (
            <MaterialDetailPanel
              doc={selected.doc}
              sessionIndex={selected.sessionIndex}
              onPreview={() => setPreviewId(selected.doc.id)}
              onAssign={() => setAssignId(selected.doc.id)}
              onRemove={() => setRemoveId(selected.doc.id)}
            />
          ) : null}
        </div>
      )}

      <LinkResourceDialog
        open={linkOpen}
        onOpenChange={setLinkOpen}
        sessions={sessionOptions}
        onSubmit={() => {
          setLinkOpen(false);
          setNotice({
            tone: "info",
            title: t("link.unsupportedTitle"),
            reason: t("link.unsupportedBody"),
          });
        }}
      />

      {assignEntry ? (
        <AssignSessionDialog
          open={assignId != null}
          onOpenChange={(open) => !open && setAssignId(null)}
          courseId={courseId}
          doc={assignEntry.doc}
        />
      ) : null}

      {removeEntry ? (
        <RemoveMaterialDialog
          open={removeId != null}
          onOpenChange={(open) => !open && setRemoveId(null)}
          courseId={courseId}
          doc={removeEntry.doc}
          onRemoved={() => setSelectedId(null)}
        />
      ) : null}
    </section>
  );
}

function LibrarySkeleton() {
  return (
    <div className="grid gap-5 lg:grid-cols-[14rem_1fr]">
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full rounded-[var(--radius-md)]" />
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-[var(--radius-lg)]" />
    </div>
  );
}
