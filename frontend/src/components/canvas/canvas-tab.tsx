"use client";

import { useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  FolderDown,
  Loader2,
  RefreshCw,
  Users,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { FileImportDialog } from "@/components/canvas/file-import-dialog";
import { RosterImportDialog } from "@/components/canvas/roster-import-dialog";
import {
  useCanvasConnection,
  useCanvasFiles,
  useCanvasSyncEvents,
  useRunCanvasSync,
} from "@/hooks/use-canvas";
import { CanvasConnectButton } from "@/components/canvas/connect-button";
import { formatRelativeTime } from "@/lib/format";
import type { CanvasSyncEvent } from "@/lib/canvas-api";

interface CanvasTabProps {
  readonly meliCourseId: string;
}

export function CanvasTab({ meliCourseId }: CanvasTabProps) {
  const { data: connection, isLoading: connLoading } = useCanvasConnection();
  const connected = connection?.connected === true;

  const { data: files, isLoading: filesLoading } = useCanvasFiles(
    meliCourseId,
    connected
  );
  const { data: events, isLoading: eventsLoading } =
    useCanvasSyncEvents(meliCourseId);
  const runSync = useRunCanvasSync(meliCourseId);

  const [filesOpen, setFilesOpen] = useState(false);
  const [rosterOpen, setRosterOpen] = useState(false);

  if (connLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!connected) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Connect Canvas</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-[var(--color-text-muted)]">
            Connect your Canvas account to import files and sync the roster
            for this course.
          </p>
          <CanvasConnectButton />
        </CardContent>
      </Card>
    );
  }

  const availableCount = files?.available.length ?? 0;
  const importedCount = files?.already_imported.length ?? 0;

  return (
    <div className="space-y-6">
      {/* Sync now */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="size-4" />
            Canvas sync
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[var(--color-text-muted)]">
            Pull the latest file list and roster diff from Canvas now.
          </p>
          <Button
            variant="outline"
            onClick={() => runSync.mutate()}
            disabled={runSync.isPending}
          >
            {runSync.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            {runSync.isPending ? "Syncing…" : "Sync now"}
          </Button>
        </CardContent>
      </Card>

      {/* Files */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderDown className="size-4" />
            Files
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {filesLoading ? (
            <Skeleton className="h-5 w-48" />
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">
              {availableCount} available in Canvas · {importedCount} already
              imported
            </p>
          )}
          <Button
            onClick={() => setFilesOpen(true)}
            disabled={availableCount === 0}
          >
            <FolderDown className="size-4" />
            Import files
          </Button>
        </CardContent>
      </Card>

      {/* Roster */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="size-4" />
            Roster
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-[var(--color-text-muted)]">
            Sync the Canvas roster into this Meli course.
          </p>
          <Button onClick={() => setRosterOpen(true)}>
            <Users className="size-4" />
            Import roster
          </Button>
        </CardContent>
      </Card>

      {/* Recent sync events */}
      <Card>
        <CardHeader>
          <CardTitle>Recent sync activity</CardTitle>
        </CardHeader>
        <CardContent>
          {eventsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (events?.length ?? 0) === 0 ? (
            <p className="py-4 text-center text-sm text-[var(--color-text-muted)]">
              No sync events yet.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {(events ?? []).map((ev) => (
                <SyncEventRow key={ev.id} event={ev} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <FileImportDialog
        courseId={meliCourseId}
        open={filesOpen}
        onOpenChange={setFilesOpen}
      />
      <RosterImportDialog
        courseId={meliCourseId}
        open={rosterOpen}
        onOpenChange={setRosterOpen}
      />
    </div>
  );
}

function SyncEventRow({ event }: { event: CanvasSyncEvent }) {
  const isError = event.status === "error" || event.status === "failed";
  const isSuccess = event.status === "success" || event.status === "ok";
  return (
    <li className="flex items-start gap-3 py-2 first:pt-0 last:pb-0">
      {isError ? (
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-[var(--color-error)]" />
      ) : isSuccess ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-[var(--color-success)]" />
      ) : (
        <RefreshCw className="mt-0.5 size-4 shrink-0 text-[var(--color-text-muted)]" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm text-[var(--color-text)]">
          <span className="font-medium">{event.event_type}</span>
          {event.summary ? (
            <span className="text-[var(--color-text-muted)]"> — {event.summary}</span>
          ) : null}
        </p>
        <p className="text-xs text-[var(--color-text-muted)]">
          {formatRelativeTime(event.created_at)} · {event.status}
        </p>
      </div>
    </li>
  );
}
