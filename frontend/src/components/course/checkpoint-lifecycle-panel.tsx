"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Loader2, Rocket, SquareCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import { ApiError } from "@/lib/api";
import {
  useApproveCheckpoint,
  useCloseCheckpoint,
  type Checkpoint,
  type CheckpointStatus,
} from "@/hooks/use-checkpoints";

import { PublishGateDialog } from "./publish-gate-dialog";
import { QrLaunchPanel } from "./qr-launch-panel";
import { CheckpointMonitor } from "./checkpoint-monitor";
import { CheckpointResultsView } from "./checkpoint-results-view";

interface CheckpointLifecyclePanelProps {
  readonly courseId: string;
  readonly checkpoint: Checkpoint;
}

const APPROVABLE: readonly CheckpointStatus[] = ["draft", "teacher_editing"];
const PUBLISHABLE: readonly CheckpointStatus[] = ["approved", "scheduled"];
const RUNNING: readonly CheckpointStatus[] = ["published", "live"];
const DONE: readonly CheckpointStatus[] = ["closed", "archived"];

/**
 * T18 lifecycle orchestrator mounted into the studio (T040). It drives the
 * publish path off the checkpoint's status: approve a draft, publish an approved
 * checkpoint through the gate dialog (T044), then run it — QR launch (T045) +
 * live monitor (T046) with a close action — before it lands in its closed
 * results state (surfaced in T19). Each transition maps a typed
 * `REVIEW_REQUIRED` refusal to an inline blocked message.
 */
export function CheckpointLifecyclePanel({
  courseId,
  checkpoint,
}: CheckpointLifecyclePanelProps) {
  const t = useTranslations("teacher.checkpoint.lifecycle");
  const approve = useApproveCheckpoint(courseId, checkpoint.id);
  const close = useCloseCheckpoint(courseId, checkpoint.id);
  const [publishOpen, setPublishOpen] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);

  const { status } = checkpoint;

  const runApprove = useCallback(async () => {
    setGateError(null);
    try {
      await approve.mutateAsync();
    } catch (error) {
      setGateError(
        error instanceof ApiError && error.code === "REVIEW_REQUIRED"
          ? (error.detail ?? t("approveError"))
          : t("approveError")
      );
    }
  }, [approve, t]);

  const runClose = useCallback(async () => {
    setGateError(null);
    try {
      await close.mutateAsync();
    } catch {
      setGateError(t("closeError"));
    }
  }, [close, t]);

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface-hover)]/40 p-5">
      <div className="space-y-1">
        <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
          {t("title")}
        </h3>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t(`hint.${status}`)}
        </p>
      </div>

      {APPROVABLE.includes(status) ? (
        <Button
          type="button"
          disabled={approve.isPending}
          onClick={() => void runApprove()}
        >
          {approve.isPending ? (
            <Loader2 aria-hidden="true" className="animate-spin" />
          ) : (
            <CheckCircle2 aria-hidden="true" />
          )}
          {t("approve")}
        </Button>
      ) : null}

      {PUBLISHABLE.includes(status) ? (
        <>
          <Button type="button" onClick={() => setPublishOpen(true)}>
            <Rocket aria-hidden="true" />
            {t("publish")}
          </Button>
          <PublishGateDialog
            open={publishOpen}
            onOpenChange={setPublishOpen}
            courseId={courseId}
            checkpoint={checkpoint}
          />
        </>
      ) : null}

      {RUNNING.includes(status) ? (
        <div className="space-y-4">
          <QrLaunchPanel checkpointId={checkpoint.id} />
          <CheckpointMonitor checkpointId={checkpoint.id} enabled />
          <Button
            type="button"
            variant="outline"
            disabled={close.isPending}
            onClick={() => void runClose()}
          >
            {close.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <SquareCheck aria-hidden="true" />
            )}
            {t("close")}
          </Button>
        </div>
      ) : null}

      {DONE.includes(status) ? (
        <div className="space-y-4">
          <StateBanner
            tone="success"
            title={t("closedTitle")}
            reason={t("closedReason")}
          />
          <CheckpointResultsView checkpointId={checkpoint.id} />
        </div>
      ) : null}

      {gateError ? (
        <StateBanner tone="blocked" title={t("blockedTitle")} reason={gateError} />
      ) : null}
    </section>
  );
}
