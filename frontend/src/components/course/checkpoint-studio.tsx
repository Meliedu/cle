"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, MessageSquare, Repeat2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import {
  useCheckpoint,
  useCheckpoints,
  useCheckpointHistory,
  type Checkpoint,
  type CheckpointStatus,
} from "@/hooks/use-checkpoints";

import { StatusChip, checkpointTone } from "./session-status";
import { CheckpointCardEditor } from "./checkpoint-card-editor";
import { CarryOverDialog } from "./carry-over-dialog";

interface CheckpointStudioProps {
  readonly courseId: string;
  readonly meetingId: string;
  readonly checkpointId: string;
}

/** Cards are editable only while the checkpoint is still in draft (P1 gate). */
const EDITABLE_STATUSES: readonly CheckpointStatus[] = ["draft", "teacher_editing"];

function isCardEditable(status: CheckpointStatus): boolean {
  return EDITABLE_STATUSES.includes(status);
}

/**
 * T040 — checkpoint studio by session. The container the teacher works a single
 * checkpoint in: it shows the checkpoint's live status (one chip per state,
 * shared with the sessions surfaces), lists its cards for review/edit (T041) +
 * removal-with-reason (T042), and surfaces a carry-over lineage banner when the
 * checkpoint is a follow-up (T043). The publish-path lifecycle actions (approve /
 * publish / QR / live monitor) mount into the `<footer>` slot in T18.
 */
export function CheckpointStudio({
  courseId,
  meetingId,
  checkpointId,
}: CheckpointStudioProps) {
  const t = useTranslations("teacher.studio");
  const { data: checkpoint, isLoading } = useCheckpoint(checkpointId);
  const { data: draftCheckpoints } = useCheckpoints(courseId);
  const { data: historyCheckpoints } = useCheckpointHistory(courseId);
  const [actionError, setActionError] = useState<string | null>(null);
  const [carryOpen, setCarryOpen] = useState(false);

  const sessionHref = `/teacher/courses/${courseId}/sessions/${meetingId}`;
  const studioBase = `/teacher/courses/${courseId}/sessions/${meetingId}/checkpoints`;

  const carriedSource: Checkpoint | null = useMemo(() => {
    if (!checkpoint?.carried_from_id) return null;
    const all = [...(draftCheckpoints ?? []), ...(historyCheckpoints ?? [])];
    return all.find((cp) => cp.id === checkpoint.carried_from_id) ?? null;
  }, [checkpoint?.carried_from_id, draftCheckpoints, historyCheckpoints]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-48 w-full rounded-[var(--radius-xl)]" />
      </div>
    );
  }

  if (!checkpoint) {
    return (
      <StateBanner
        tone="warning"
        title={t("notFound.title")}
        reason={t("notFound.reason")}
        action={
          <Button size="sm" variant="outline" render={<Link href={sessionHref} />}>
            {t("backToSession")}
          </Button>
        }
      />
    );
  }

  const editable = isCardEditable(checkpoint.status);
  const cards = checkpoint.cards ?? [];

  return (
    <div className="space-y-6">
      <Link
        href={sessionHref}
        className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-text-muted)] transition-colors hover:text-[var(--color-text)]"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" />
        {t("backToSession")}
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("eyebrow")}
            </span>
            <StatusChip
              tone={checkpointTone(checkpoint.status)}
              label={t(`status.${checkpoint.status}`)}
            />
          </div>
          <h2 className="text-[20px] font-semibold tracking-tight text-[var(--color-text)]">
            {checkpoint.title}
          </h2>
          <p className="max-w-[60ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {editable ? t("subtitle") : t("subtitleLocked")}
          </p>
        </div>
      </div>

      {checkpoint.carried_from_id ? (
        <StateBanner
          tone="info"
          title={t("carryOver.bannerTitle")}
          reason={t("carryOver.bannerReason")}
          action={
            <Button
              size="sm"
              variant="outline"
              onClick={() => setCarryOpen(true)}
            >
              <Repeat2 aria-hidden="true" />
              {t("carryOver.review")}
            </Button>
          }
        />
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("cards.title")}
          </h3>
          <span className="text-[12px] text-[var(--color-text-muted)]">
            {t("cards.count", { count: cards.filter((c) => !c.removed).length })}
          </span>
        </div>

        {cards.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title={t("cards.emptyTitle")}
            reason={t("cards.emptyReason")}
          />
        ) : (
          <ol className="space-y-2.5">
            {cards.map((card, index) => (
              <CheckpointCardEditor
                key={card.id}
                courseId={courseId}
                checkpointId={checkpointId}
                card={card}
                position={index + 1}
                editable={editable}
                onError={setActionError}
              />
            ))}
          </ol>
        )}

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}
      </section>

      <CarryOverDialog
        open={carryOpen}
        onOpenChange={setCarryOpen}
        checkpoint={checkpoint}
        source={carriedSource}
        sourceHref={
          carriedSource
            ? `${studioBase}/${carriedSource.id}`
            : undefined
        }
      />
    </div>
  );
}
