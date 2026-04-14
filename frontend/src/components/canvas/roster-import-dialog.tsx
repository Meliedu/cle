"use client";

import { useState } from "react";
import { Loader2, Users } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useImportCanvasRoster } from "@/hooks/use-canvas";
import type { CanvasRosterImportResult } from "@/lib/canvas-api";

interface RosterImportDialogProps {
  readonly courseId: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

export function RosterImportDialog({
  courseId,
  open,
  onOpenChange,
}: RosterImportDialogProps) {
  const importRoster = useImportCanvasRoster(courseId);
  const [sendInvite, setSendInvite] = useState(false);
  const [lastResult, setLastResult] =
    useState<CanvasRosterImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    setError(null);
    try {
      const result = await importRoster.mutateAsync(sendInvite);
      setLastResult(result);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to import roster"
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="size-4" />
            Import roster from Canvas
          </DialogTitle>
          <DialogDescription>
            Sync the Canvas student roster into this Meli course. Students
            already enrolled stay unchanged; dropped students are removed.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={sendInvite}
              onChange={(e) => setSendInvite(e.target.checked)}
              className="mt-0.5 size-4 cursor-pointer"
            />
            <span>
              <span className="text-[var(--color-text)]">Send invite emails</span>
              <span className="block text-xs text-[var(--color-text-muted)]">
                Email newly-added students a link to sign in and access Meli.
              </span>
            </span>
          </label>

          {error && (
            <p className="text-sm text-[var(--color-error)]">{error}</p>
          )}

          {lastResult && (
            <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm">
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                <span className="text-[var(--color-text-muted)]">Added</span>
                <span className="text-[var(--color-success)]">
                  {lastResult.added}
                </span>
                <span className="text-[var(--color-text-muted)]">Unchanged</span>
                <span>{lastResult.unchanged}</span>
                <span className="text-[var(--color-text-muted)]">Dropped</span>
                <span>{lastResult.dropped}</span>
                <span className="text-[var(--color-text-muted)]">
                  Pending (invited)
                </span>
                <span>{lastResult.pending}</span>
                <span className="text-[var(--color-text-muted)]">
                  Skipped (off-domain)
                </span>
                <span>{lastResult.skipped_off_domain}</span>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={importRoster.isPending}
          >
            Close
          </Button>
          <Button
            onClick={handleImport}
            disabled={importRoster.isPending}
          >
            {importRoster.isPending && (
              <Loader2 className="size-4 animate-spin" />
            )}
            {importRoster.isPending ? "Importing…" : "Import roster"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
