"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  MessageSquare,
  Pencil,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState, StateBanner } from "@/components/patterns";
import { setupErrorCode, useGenerateCheckpoints, useSetStep } from "@/hooks/use-setup";
import {
  useCheckpoint,
  useCheckpoints,
  useUpdateCheckpointCard,
  type Checkpoint,
  type CheckpointCard,
  type RemovedReason,
} from "@/hooks/use-checkpoints";

interface StepCheckpointsProps {
  readonly courseId: string;
  /** Fired after the `checkpoints` checklist flag is set. */
  readonly onComplete?: () => void;
}

const REMOVE_REASONS: readonly RemovedReason[] = [
  "not_needed",
  "duplicate",
  "not_covered",
  "other",
];

const SELECT_CLASS =
  "h-8 w-full min-w-0 rounded-lg border border-[var(--color-border)] bg-transparent px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";

/**
 * T022 — checkpoint-generation-review step. Enqueues the grounded
 * `generate_checkpoints` job (`useGenerateCheckpoints`), polls the course
 * checkpoint list until drafts appear (`useCheckpoints`), and lets the teacher
 * review each DRAFT checkpoint's cards (`useCheckpoint`): light-edit a
 * review-point prompt or remove one with a reason (`useUpdateCheckpointCard`),
 * respecting the fixed final-comments card (`FINAL_CARD_FIXED`). Full publish /
 * scheduling is P3 (Decision 3) — everything here is draft-only. "Continue"
 * flips the `checkpoints` flag once at least one draft exists.
 */
export function StepCheckpoints({ courseId, onComplete }: StepCheckpointsProps) {
  const t = useTranslations("teacher.setup.checkpoints");
  const setStep = useSetStep(courseId);
  const [started, setStarted] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data: checkpoints, isLoading } = useCheckpoints(courseId, { poll: started });
  const generate = useGenerateCheckpoints(courseId);

  const drafts = useMemo(() => checkpoints ?? [], [checkpoints]);
  const hasDrafts = drafts.length > 0;
  const isGenerating = started && !hasDrafts;

  const runGenerate = useCallback(async () => {
    setActionError(null);
    setStarted(true);
    try {
      await generate.mutateAsync();
    } catch {
      setActionError(t("generateError"));
    }
  }, [generate, t]);

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "checkpoints", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const isFlipping = setStep.isPending;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size={hasDrafts ? "sm" : "lg"}
            variant={hasDrafts ? "outline" : "default"}
            disabled={generate.isPending || isGenerating}
            onClick={() => void runGenerate()}
          >
            {generate.isPending || isGenerating ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {hasDrafts ? t("regenerate") : t("generate")}
          </Button>
        </div>

        {hasDrafts ? (
          <StateBanner tone="info" title={t("draftNotice.title")} reason={t("draftNotice.reason")} />
        ) : null}

        {isLoading || isGenerating ? (
          <EmptyState variant="waiting" title={t("generating.title")} reason={t("generating.reason")} />
        ) : !hasDrafts ? (
          <EmptyState
            variant="empty"
            icon={Sparkles}
            title={t("empty.title")}
            reason={t("empty.reason")}
          />
        ) : (
          <ul className="space-y-3">
            {drafts.map((checkpoint) => (
              <CheckpointItem
                key={checkpoint.id}
                courseId={courseId}
                checkpoint={checkpoint}
                onError={setActionError}
                t={t}
              />
            ))}
          </ul>
        )}

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={!hasDrafts || isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
            {t("continue")}
          </Button>
        </div>
      </div>

      <ConfidenceAside t={t} />
    </div>
  );
}

interface CheckpointItemProps {
  readonly courseId: string;
  readonly checkpoint: Checkpoint;
  readonly onError: (message: string | null) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function CheckpointItem({ courseId, checkpoint, onError, t }: CheckpointItemProps) {
  const [expanded, setExpanded] = useState(false);
  const { data, isLoading } = useCheckpoint(expanded ? checkpoint.id : null);
  const cards = data?.cards ?? [];

  return (
    <li className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--color-primary)]"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          {expanded ? (
            <ChevronDown aria-hidden="true" className="size-4 shrink-0 text-[var(--color-text-muted)]" />
          ) : (
            <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-[var(--color-text-muted)]" />
          )}
          <span className="truncate text-[13px] font-semibold text-[var(--color-text)]">
            {checkpoint.title}
          </span>
        </div>
        <Badge variant="secondary">{t("draft")}</Badge>
      </button>

      {expanded ? (
        <div className="border-t border-[var(--color-border)] p-4">
          {isLoading ? (
            <EmptyState variant="waiting" title={t("cardsLoading")} />
          ) : cards.length === 0 ? (
            <EmptyState variant="empty" icon={MessageSquare} title={t("noCards")} />
          ) : (
            <ol className="space-y-2.5">
              {cards.map((card, index) => (
                <CardRow
                  key={card.id}
                  courseId={courseId}
                  checkpointId={checkpoint.id}
                  card={card}
                  position={index + 1}
                  onError={onError}
                  t={t}
                />
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </li>
  );
}

interface CardRowProps {
  readonly courseId: string;
  readonly checkpointId: string;
  readonly card: CheckpointCard;
  readonly position: number;
  readonly onError: (message: string | null) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function CardRow({ courseId, checkpointId, card, position, onError, t }: CardRowProps) {
  const update = useUpdateCheckpointCard(courseId, checkpointId);
  const [mode, setMode] = useState<"view" | "edit" | "remove">("view");
  const [prompt, setPrompt] = useState(card.prompt);
  const [reason, setReason] = useState<RemovedReason>("not_needed");

  const isFinal = card.kind === "final_comments";

  const saveEdit = useCallback(async () => {
    onError(null);
    try {
      await update.mutateAsync({ cardId: card.id, prompt: prompt.trim() });
      setMode("view");
    } catch (error) {
      onError(t(`errors.${setupErrorCode(error) ?? "generic"}`));
    }
  }, [update, card.id, prompt, onError, t]);

  const confirmRemove = useCallback(async () => {
    onError(null);
    try {
      await update.mutateAsync({ cardId: card.id, removed: true, removedReason: reason });
    } catch (error) {
      onError(t(`errors.${setupErrorCode(error) ?? "generic"}`));
    }
  }, [update, card.id, reason, onError, t]);

  return (
    <li className="flex gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-primary-light)] text-[12px] font-semibold text-[var(--color-primary-hover)]">
        {position}
      </span>

      <div className="min-w-0 flex-1 space-y-2">
        {mode === "edit" ? (
          <div className="space-y-2">
            <Textarea
              aria-label={t("promptLabel", { position })}
              rows={2}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                disabled={update.isPending || !prompt.trim()}
                onClick={() => void saveEdit()}
              >
                {update.isPending ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
                {t("save")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setPrompt(card.prompt);
                  setMode("view");
                }}
              >
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : mode === "remove" ? (
          <div className="space-y-2">
            <p className="text-[13px] text-[var(--color-text)]">{card.prompt}</p>
            <label className="block text-[12px] font-medium text-[var(--color-text-secondary)]">
              {t("removeReason")}
            </label>
            <select
              aria-label={t("removeReason")}
              className={SELECT_CLASS}
              value={reason}
              onChange={(e) => setReason(e.target.value as RemovedReason)}
            >
              {REMOVE_REASONS.map((r) => (
                <option key={r} value={r}>
                  {t(`reason.${r}`)}
                </option>
              ))}
            </select>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="destructive"
                disabled={update.isPending}
                onClick={() => void confirmRemove()}
              >
                {update.isPending ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
                {t("confirmRemove")}
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setMode("view")}>
                {t("cancel")}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-[13px] leading-relaxed text-[var(--color-text)]">{card.prompt}</p>
            <div className="flex items-center gap-1.5">
              <Badge variant="outline">
                {isFinal ? t("kind.final_comments") : t("kind.review_point")}
              </Badge>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setPrompt(card.prompt);
                  setMode("edit");
                }}
              >
                <Pencil aria-hidden="true" />
                {t("edit")}
              </Button>
              {isFinal ? (
                <span className="inline-flex items-center gap-1 text-[12px] text-[var(--color-text-muted)]">
                  <X aria-hidden="true" className="size-3.5" />
                  {t("fixed")}
                </span>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="text-[var(--color-error)]"
                  onClick={() => setMode("remove")}
                >
                  <Trash2 aria-hidden="true" />
                  {t("remove")}
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </li>
  );
}

function ConfidenceAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const scale = ["1", "2", "3", "4", "5"] as const;
  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <p className="mt-2 text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("aside.description")}
      </p>
      <div className="mt-4 flex items-center justify-between">
        {scale.map((n) => (
          <span
            key={n}
            className="flex size-8 items-center justify-center rounded-full border border-[var(--color-border)] text-[13px] font-semibold text-[var(--color-text-secondary)]"
          >
            {n}
          </span>
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
        <span>{t("aside.low")}</span>
        <span>{t("aside.high")}</span>
      </div>
    </aside>
  );
}
