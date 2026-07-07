"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Upload, LinkIcon, FolderPlus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useMaterials } from "@/hooks/use-documents";
import { MaterialsFolderNav, ALL_FOLDER } from "./materials-folder-nav";
import { MaterialsTable } from "./materials-table";
import { MaterialsUploadPanel } from "./materials-upload-panel";
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

/**
 * T052–T054 — teacher materials library orchestrator. Composes the session-
 * folder rail (`useMaterials` grouping), the materials table, the upload panel
 * (reusing `UploadZone`), and the add-link modal. Selection + preview/assign/
 * remove land in F7; this task ships the browse + ingest surface.
 */
export function MaterialsLibrary({ courseId }: MaterialsLibraryProps) {
  const t = useTranslations("teacher.materials");
  const { data: library, isLoading, isError } = useMaterials(courseId);

  const [folder, setFolder] = useState<string>(ALL_FOLDER);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [linkOpen, setLinkOpen] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

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
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setNotice(null)}
            >
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
        <EmptyState
          icon={FolderPlus}
          title={t("empty.title")}
          reason={t("empty.reason")}
          action={
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => setUploadOpen(true)}
                data-icon="inline-start"
              >
                <Upload aria-hidden="true" />
                {t("empty.upload")}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setLinkOpen(true)}
                data-icon="inline-start"
              >
                <LinkIcon aria-hidden="true" />
                {t("empty.addLink")}
              </Button>
            </div>
          }
        />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[14rem_1fr]">
          <MaterialsFolderNav
            library={library}
            selected={folder}
            onSelect={setFolder}
          />
          <MaterialsTable library={library} folder={folder} />
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
