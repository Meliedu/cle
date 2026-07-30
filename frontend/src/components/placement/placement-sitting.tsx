"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";

import { StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import {
  PlacementQuestion,
  isCompleteOrder,
} from "@/components/placement/placement-question";
import { PlacementTimer } from "@/components/placement/placement-timer";
import { cn } from "@/lib/utils";
import {
  useReportInterruption,
  useSavePlacementResponse,
  useSubmitPlacementAttempt,
  type PlacementAttemptDetail,
  type PlacementSection,
} from "@/hooks/use-placement";

interface PlacementSittingProps {
  readonly attempt: PlacementAttemptDetail;
  readonly onSubmitted: () => void;
}

const SECTION_ORDER: readonly PlacementSection[] = [
  "listening",
  "language_use",
  "reading",
];

/**
 * The timed sitting.
 *
 * Answers live in local state and are pushed to the server as they change.
 * Local state is the source of truth for what the learner sees, because a
 * network round trip must never be able to blank or revert an input they are
 * looking at. The server is the source of truth for what counts, which is why
 * submission does not depend on the autosave queue having drained: it sends any
 * still-unsaved answer first.
 */
export function PlacementSitting({ attempt, onSubmitted }: PlacementSittingProps) {
  const t = useTranslations("placement.sitting");
  const save = useSavePlacementResponse(attempt.id);
  const submit = useSubmitPlacementAttempt(attempt.id);
  const reportInterruption = useReportInterruption(attempt.id);

  const [answers, setAnswers] = useState<Record<string, string | null>>(
    () => ({ ...attempt.saved_responses })
  );
  const [index, setIndex] = useState(0);
  const [plays, setPlays] = useState<Record<string, number>>({});
  const [saveFailed, setSaveFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [expired, setExpired] = useState(false);
  /** Question numbers whose answer could not be saved, blocking submission. */
  const [unsavedQuestions, setUnsavedQuestions] = useState<number[]>([]);

  const items = attempt.items;
  const current = items[index];
  const questionRef = useRef<HTMLDivElement>(null);
  // Set in the effect below, not here: reading the clock during render is
  // impure and would produce a different value on every re-render.
  const seenAt = useRef<number>(0);
  /** Answers whose save failed, retried on the next change and before submit. */
  const pending = useRef<Map<string, string | null>>(new Map());

  /** Whether a held value is a legal, submittable answer for that item. */
  const isSubmittable = useCallback(
    (itemId: string, value: string | null | undefined): value is string => {
      if (!value) return false;
      const item = items.find((candidate) => candidate.id === itemId);
      if (!item) return false;
      return item.response_format === "sequence"
        ? isCompleteOrder(value, item.option_letters.length)
        : true;
    },
    [items]
  );

  // A half-finished ordering item is on screen but is not an answer, so it must
  // not inflate the progress bar or the "you have answered everything" copy.
  const answeredCount = useMemo(
    () => items.filter((item) => isSubmittable(item.id, answers[item.id])).length,
    [answers, isSubmittable, items]
  );

  useEffect(() => {
    seenAt.current = Date.now();
    // Move focus to the question when the learner pages, so keyboard and
    // screen-reader users land on the new content instead of staying on a
    // button that has just changed meaning.
    questionRef.current?.focus();
  }, [index]);

  /** Returns whether the answer actually reached the server. */
  const persist = useCallback(
    async (itemId: string, value: string | null): Promise<boolean> => {
      try {
        await save.mutateAsync({
          item_id: itemId,
          response: value,
          time_spent_ms: Math.max(0, Date.now() - seenAt.current),
          audio_play_count: plays[itemId],
        });
        pending.current.delete(itemId);
        if (pending.current.size === 0) setSaveFailed(false);
        return true;
      } catch {
        // Keep the answer locally and flag it. Losing a learner's response to a
        // dropped packet is the worst failure this screen has.
        pending.current.set(itemId, value);
        setSaveFailed(true);
        return false;
      }
    },
    [plays, save]
  );

  const handleChange = useCallback(
    (value: string | null) => {
      if (!current) return;
      // Always keep what the learner sees; only send what the server accepts.
      setAnswers((prev) => ({ ...prev, [current.id]: value }));
      void persist(
        current.id,
        isSubmittable(current.id, value) ? value : null
      );
      // Opportunistically retry anything still unsaved.
      for (const [itemId, queued] of [...pending.current]) {
        if (itemId !== current.id) void persist(itemId, queued);
      }
    },
    [current, isSubmittable, persist]
  );

  const handlePlay = useCallback(() => {
    if (!current) return;
    setPlays((prev) => ({ ...prev, [current.id]: (prev[current.id] ?? 0) + 1 }));
  }, [current]);

  useEffect(() => {
    // A learner who loses connectivity mid-sitting produces evidence a reviewer
    // needs; recording it is what turns "their score looks odd" into "their
    // network dropped for four minutes".
    const onOffline = () => {
      reportInterruption.mutate({ kind: "offline" });
    };
    window.addEventListener("offline", onOffline);
    return () => window.removeEventListener("offline", onOffline);
  }, [reportInterruption]);

  /**
   * @param force submit even if an answer could not be saved.
   *
   * Only the timer path forces. Past `expires_at + grace` the server rejects
   * every save, so a flush can never succeed again: blocking submission there
   * would strand the whole attempt to protect one answer, and the alert
   * explaining why is inside the confirm dialog, which the timer never opens.
   * Losing one unsaved answer beats losing the sitting.
   */
  const handleSubmit = useCallback(async (force = false) => {
    // Flush anything the autosave never landed, and CHECK whether it landed.
    // `persist` swallows its own errors so the sitting keeps working, which
    // meant this loop used to complete identically whether the flush succeeded
    // or not -- and submission would then close the attempt without a learner's
    // answer, while the banner saying so unmounted with the screen.
    const stillUnsaved: number[] = [];
    for (const [itemId, queued] of [...pending.current]) {
      const ok = await persist(itemId, queued);
      if (!ok) {
        const item = items.find((candidate) => candidate.id === itemId);
        if (item) stillUnsaved.push(item.question_number);
      }
    }
    if (stillUnsaved.length > 0 && !force) {
      setUnsavedQuestions(stillUnsaved.sort((a, b) => a - b));
      return;
    }
    setUnsavedQuestions([]);

    try {
      await submit.mutateAsync();
      onSubmitted();
    } catch {
      setConfirming(false);
    }
  }, [items, onSubmitted, persist, submit]);

  const handleExpire = useCallback(() => {
    setExpired(true);
    // Force: saves are already rejected, so a blocked submit would strand the
    // whole attempt rather than protect an answer.
    void handleSubmit(true);
  }, [handleSubmit]);

  if (!current) {
    return (
      <StateBanner
        tone="waiting"
        title={t("loadingTitle")}
        reason={t("loadingReason")}
      />
    );
  }

  const sectionIndex = SECTION_ORDER.indexOf(current.section);

  return (
    <div className="space-y-6">
      {/* Sticky header: which section, how far, how long left. */}
      <header className="sticky top-0 z-10 border-b border-[var(--color-border)] bg-[var(--color-bg)]/95 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-[13px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-secondary)]">
              {t(`section.${current.section}`)}
            </span>
            <span className="text-[13px] text-[var(--color-text-secondary)]">
              {t("progress", {
                current: index + 1,
                total: items.length,
              })}
            </span>
          </div>
          {attempt.expires_at ? (
            <PlacementTimer expiresAt={attempt.expires_at} onExpire={handleExpire} />
          ) : null}
        </div>

        <div
          className="mt-3 h-1.5 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={items.length}
          aria-valuenow={answeredCount}
          aria-label={t("answeredOf", {
            answered: answeredCount,
            total: items.length,
          })}
        >
          <div
            className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)] transition-[width] duration-200"
            style={{ width: `${(answeredCount / items.length) * 100}%` }}
          />
        </div>
      </header>

      {saveFailed ? (
        <StateBanner
          tone="warning"
          title={t("saveFailedTitle")}
          reason={t("saveFailedReason")}
        />
      ) : null}

      {expired ? (
        <StateBanner tone="blocked" title={t("expiredTitle")} reason={t("expiredReason")} />
      ) : null}

      <div
        ref={questionRef}
        tabIndex={-1}
        className="outline-none"
        aria-labelledby="placement-question-heading"
      >
        <h2
          id="placement-question-heading"
          className="mb-4 text-[15px] font-semibold text-[var(--color-text)]"
        >
          {t("questionHeading", { number: current.question_number })}
        </h2>
        <PlacementQuestion
          item={current}
          value={answers[current.id] ?? null}
          onChange={handleChange}
          playCount={plays[current.id] ?? 0}
          onPlay={handlePlay}
          audioAvailable={attempt.audio_available}
        />
      </div>


      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] pt-5">
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={() => setIndex((value) => Math.max(0, value - 1))}
          disabled={index === 0}
        >
          <ChevronLeft aria-hidden="true" />
          {t("previous")}
        </Button>

        {index < items.length - 1 ? (
          <Button
            type="button"
            size="lg"
            onClick={() => setIndex((value) => Math.min(items.length - 1, value + 1))}
          >
            {t("next")}
            <ChevronRight aria-hidden="true" />
          </Button>
        ) : (
          <Button type="button" size="lg" onClick={() => setConfirming(true)}>
            {t("reviewAndSubmit")}
          </Button>
        )}
      </div>

      {/* Question map: every question reachable in one action, and unanswered
          ones are visibly distinct so nothing is missed by accident. */}
      <nav aria-label={t("questionMapLabel")}>
        <ul className="flex flex-wrap gap-1.5">
          {items.map((item, itemIndex) => {
            // `isSubmittable`, not `Boolean`: a half-filled ordering item is on
            // screen but is not an answer. Marking it answered here (while the
            // counter disagrees) would tell a learner every question is done
            // and give them no way to find the one that is not.
            const held = answers[item.id];
            const answered = isSubmittable(item.id, held);
            const started = Boolean(held) && !answered;
            const isCurrent = itemIndex === index;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setIndex(itemIndex)}
                  aria-current={isCurrent ? "true" : undefined}
                  aria-label={t(
                    answered
                      ? "goToAnswered"
                      : started
                        ? "goToStarted"
                        : "goToUnanswered",
                    { number: item.question_number }
                  )}
                  className={cn(
                    "size-9 rounded-[var(--radius-md)] border text-[13px] font-medium tabular-nums",
                    "pointer-coarse:size-11 transition-colors duration-150",
                    "outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40",
                    isCurrent
                      ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-[var(--color-text-on-primary)]"
                      : answered
                        ? "border-[var(--color-border-hover)] bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                        : started
                          // Started but not finishable: its own treatment, so
                          // the one ordering item left half-done is findable.
                          ? "border-[var(--color-warning)] bg-[var(--color-warning-light)] text-[var(--color-text)]"
                          : "border-dashed border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)]"
                  )}
                >
                  {item.question_number}
                  {started ? <span className="sr-only"> {t("startedSuffix")}</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {confirming ? (
        <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle
              aria-hidden="true"
              className="mt-0.5 size-5 shrink-0 text-[var(--color-text-secondary)]"
              strokeWidth={1.9}
            />
            <div className="flex-1">
              <h3 className="text-[15px] font-semibold text-[var(--color-text)]">
                {t("confirmTitle")}
              </h3>
              <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
                {answeredCount < items.length
                  ? t("confirmUnanswered", {
                      unanswered: items.length - answeredCount,
                    })
                  : t("confirmAll")}
              </p>
              {/* Which ones, not just how many: this is the last screen before
                  an irreversible submit, and "3 unanswered" gives a learner no
                  way to find them on a clock. */}
              {answeredCount < items.length ? (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {items
                    .filter((item) => !isSubmittable(item.id, answers[item.id]))
                    .map((item) => (
                      <li key={item.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setIndex(items.indexOf(item));
                            setConfirming(false);
                          }}
                          className="rounded-[var(--radius-sm)] border border-[var(--color-border)] px-2 py-1 text-[13px] tabular-nums text-[var(--color-text)] outline-none hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 pointer-coarse:min-h-11"
                        >
                          {t("goToQuestion", { number: item.question_number })}
                        </button>
                      </li>
                    ))}
                </ul>
              ) : null}
              <p className="mt-2 text-[13px] text-[var(--color-text-secondary)]">
                {t("confirmFinal")}
              </p>
            </div>
          </div>

          {/* Submission is blocked, not merely warned about: closing the
              attempt now would discard an answer the learner gave. */}
          {unsavedQuestions.length > 0 ? (
            <div
              role="alert"
              className="mt-4 rounded-[var(--radius-lg)] border border-[var(--color-error)]/40 bg-[var(--color-error)]/8 p-3"
            >
              <p className="text-[14px] font-medium text-[var(--color-error)]">
                {t("unsavedTitle")}
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                {t("unsavedReason", { questions: unsavedQuestions.join(", ") })}
              </p>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              type="button"
              size="lg"
              onClick={() => handleSubmit(false)}
              disabled={submit.isPending}
            >
              {submit.isPending ? t("submitting") : t("submitConfirm")}
            </Button>
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => setConfirming(false)}
              disabled={submit.isPending}
            >
              {t("keepAnswering")}
            </Button>
          </div>
          {submit.isError ? (
            <p className="mt-3 text-[13px] text-[var(--color-error)]" role="alert">
              {t("submitFailed")}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* Section context, last so it never competes with the question. */}
      <p className="text-[12px] text-[var(--color-text-secondary)]">
        {t("sectionProgress", {
          section: t(`section.${current.section}`),
          index: sectionIndex + 1,
          total: SECTION_ORDER.length,
        })}
      </p>
    </div>
  );
}
