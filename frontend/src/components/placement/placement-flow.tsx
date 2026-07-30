"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  CheckCircle2,
  ClipboardList,
  Headphones,
  Info,
  Lock,
  ShieldCheck,
} from "lucide-react";

import { EmptyState, PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PlacementSitting } from "@/components/placement/placement-sitting";
import {
  useAdvancePlacementAttempt,
  useMyPlacementAttempts,
  usePlacementAttempt,
  usePlacementIntro,
  usePlacementResult,
  useStartPlacementAttempt,
  type PlacementAttempt,
  type PlacementIntro,
} from "@/hooks/use-placement";

/**
 * The student placement surface, start to finish.
 *
 * Screens follow the spec's student flow exactly: purpose and policy, then
 * eligibility, then device and instructions, then the timed sitting, then a
 * pending state, and only after a CLE release a recommendation.
 *
 * The pending screen is the one that matters most. It is not a loading state:
 * it is the honest answer to "what is my level", which is that a person has to
 * decide, and that has not happened yet.
 */
export function PlacementFlow() {
  const t = useTranslations("placement");
  const intro = usePlacementIntro();
  const attempts = useMyPlacementAttempts();
  /** Set only when this session starts a new attempt; otherwise derived. */
  const [startedId, setStartedId] = useState<string | null>(null);

  // Resume whatever the learner already has open, or show their last result,
  // so a refresh mid-test never looks like a lost attempt.
  //
  // Derived rather than synced into state by an effect: an effect would have to
  // setState during render-commit, which cascades an extra render and needs a
  // guard against overwriting a freshly started attempt. There is nothing to
  // synchronise here, only something to compute.
  const resumable = useMemo(() => {
    const list = attempts.data;
    if (!list?.length) return null;
    const live = list.find((a) =>
      [
        "created",
        "eligibility_confirmed",
        "instructions_acknowledged",
        "in_progress",
      ].includes(a.state)
    );
    return (live ?? list[list.length - 1])?.id ?? null;
  }, [attempts.data]);

  const attemptId = startedId ?? resumable;
  const setAttemptId = setStartedId;

  if (intro.isLoading) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-2 sm:px-6" aria-busy="true">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-40 w-full" />
        <span className="sr-only">{t("loading")}</span>
      </div>
    );
  }

  // A closed test is data, not an error; a genuine fetch failure is the error.
  //
  // Never applied while the learner has an attempt in hand. The window can shut
  // mid-sitting, and a refocus refetch would otherwise replace a running exam
  // with "the screener is not open yet" while the server clock keeps going. A
  // learner who is already in only leaves through their own attempt's states.
  const closed = (intro.isError || intro.data?.available === false) && !attemptId;
  if (closed) {
    const notOpen =
      intro.data?.unavailable_reason === "not_published" ||
      intro.data?.unavailable_reason === "window_closed";
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-2 sm:px-6">
        <PageHeader title={t("title")} description={t("subtitle")} />
        <div className="mt-6">
          <EmptyState
            variant="waiting"
            icon={Lock}
            title={notOpen ? t("closed.notOpenTitle") : t("closed.unavailableTitle")}
            reason={notOpen ? t("closed.notOpenReason") : t("closed.unavailableReason")}
          />
        </div>
      </div>
    );
  }

  if (!intro.data) return null;

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 px-4 py-2 sm:px-6">
      <PageHeader title={t("title")} description={t("subtitle")} />
      <PlacementStage
        intro={intro.data}
        attemptId={attemptId}
        onAttempt={setAttemptId}
      />
    </div>
  );
}

interface PlacementStageProps {
  readonly intro: PlacementIntro;
  readonly attemptId: string | null;
  readonly onAttempt: (id: string) => void;
}

function PlacementStage({ intro, attemptId, onAttempt }: PlacementStageProps) {
  const attempt = usePlacementAttempt(attemptId);
  const tShared = useTranslations("placement");

  if (!attemptId) return <IntroScreen intro={intro} onAttempt={onAttempt} />;
  if (attempt.isLoading) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-64 w-full" />
        <span className="sr-only">{tShared("loading")}</span>
      </div>
    );
  }
  // NEVER fall through to the intro when we merely failed to load the attempt.
  // Its primary action starts a new attempt, and attempts are strictly limited,
  // so one flaky request during an exam could cost a learner a third of their
  // allowance. Say we lost contact and offer a retry instead.
  if (attempt.isError || !attempt.data) {
    return (
      <div className="space-y-4">
        <StateBanner
          tone="warning"
          title={tShared("lostContactTitle")}
          reason={tShared("lostContactReason")}
        />
        <Button type="button" size="lg" onClick={() => attempt.refetch()}>
          {tShared("retry")}
        </Button>
      </div>
    );
  }

  const state = attempt.data.state;

  if (state === "created" || state === "eligibility_confirmed") {
    return <EligibilityScreen attempt={attempt.data} intro={intro} />;
  }
  if (state === "instructions_acknowledged") {
    return <InstructionsScreen attempt={attempt.data} intro={intro} />;
  }
  if (state === "in_progress") {
    return (
      <PlacementSitting
        attempt={attempt.data}
        onSubmitted={() => attempt.refetch()}
      />
    );
  }
  return <ResultScreen attemptId={attempt.data.id} intro={intro} onRestart={onAttempt} />;
}

// ---------------------------------------------------------------------------
// 1. Purpose, privacy, structure, attempt policy
// ---------------------------------------------------------------------------

function IntroScreen({
  intro,
  onAttempt,
}: {
  readonly intro: PlacementIntro;
  readonly onAttempt: (id: string) => void;
}) {
  const t = useTranslations("placement.intro");
  // The claim boundary is the most consequential text on this page. The API
  // returns it as English prose from the booklet; it is rendered from the
  // message files instead so a zh-Hant learner does not meet the one thing
  // they most need to understand in a language they may struggle with.
  const tRoot = useTranslations("placement");
  const start = useStartPlacementAttempt();

  const handleStart = useCallback(async () => {
    const created = await start.mutateAsync();
    onAttempt(created.id);
  }, [onAttempt, start]);

  const exhausted = intro.attempts_remaining <= 0;

  return (
    <div className="space-y-6">
      {/* The claim boundary leads. A learner must know what this is before
          they know what it will say about them. */}
      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-start gap-3">
          <Info
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-[var(--color-primary-hover)]"
            strokeWidth={1.9}
          />
          <div>
            <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
              {t("purposeTitle")}
            </h2>
            <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {tRoot("purposeText")}
            </p>
          </div>
        </div>
      </div>

      <dl className="grid gap-3 sm:grid-cols-3">
        <Fact label={t("timeLabel")} value={t("timeValue", { minutes: intro.duration_minutes })} />
        <Fact label={t("itemsLabel")} value={t("itemsValue", { count: intro.total_items })} />
        <Fact
          label={t("attemptsLabel")}
          value={t("attemptsValue", {
            remaining: intro.attempts_remaining,
            total: intro.max_attempts,
          })}
        />
      </dl>

      <section>
        <h2 className="text-[13px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-secondary)]">
          {t("structureTitle")}
        </h2>
        <ul className="mt-3 space-y-2">
          {(["listening", "language_use", "reading"] as const).map((section) => (
            <li
              key={section}
              className="flex items-center justify-between rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3"
            >
              <span className="text-[15px] text-[var(--color-text)]">
                {t(`section.${section}`)}
              </span>
              <span className="text-[14px] tabular-nums text-[var(--color-text-secondary)]">
                {t("questionCount", { count: intro.section_counts[section] ?? 0 })}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {tRoot("comparabilityNote")}
        </p>
      </section>

      <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-start gap-3">
          <ShieldCheck
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-[var(--color-text-secondary)]"
            strokeWidth={1.9}
          />
          <div>
            <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
              {t("privacyTitle")}
            </h2>
            <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {tRoot("privacyText")}
            </p>
            <p className="mt-2 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
              {t("accommodation")}
            </p>
          </div>
        </div>
      </section>

      {exhausted ? (
        <StateBanner
          tone="blocked"
          title={t("exhaustedTitle")}
          reason={t("exhaustedReason", { total: intro.max_attempts })}
        />
      ) : (
        <div className="space-y-3">
          <Button
            type="button"
            size="lg"
            onClick={handleStart}
            disabled={start.isPending}
          >
            {start.isPending ? t("starting") : t("start")}
          </Button>
          {start.isError ? (
            <p className="text-[13px] text-[var(--color-error)]" role="alert">
              {t("startFailed")}
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Fact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <dt className="text-[12px] font-medium uppercase tracking-[0.12em] text-[var(--color-text-secondary)]">
        {label}
      </dt>
      <dd className="mt-1 text-[15px] font-medium text-[var(--color-text)]">{value}</dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 2. Eligibility
// ---------------------------------------------------------------------------

function EligibilityScreen({
  attempt,
  intro,
}: {
  readonly attempt: PlacementAttempt;
  readonly intro: PlacementIntro;
}) {
  const t = useTranslations("placement.eligibility");
  const advance = useAdvancePlacementAttempt(attempt.id);

  return (
    <div className="space-y-5">
      <StateBanner
        tone="info"
        title={t("allocatedTitle", { form: attempt.form_code })}
        reason={t("allocatedReason")}
      />
      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
          {t("title")}
        </h2>
        <ul className="mt-3 space-y-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          <li>{t("point1", { minutes: intro.duration_minutes })}</li>
          <li>{t("point2")}</li>
          <li>{t("point3")}</li>
        </ul>
      </div>
      <Button
        type="button"
        size="lg"
        onClick={() =>
          advance.mutate(
            attempt.state === "created"
              ? "confirm-eligibility"
              : "acknowledge-instructions"
          )
        }
        disabled={advance.isPending}
      >
        {t("confirm")}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 3. Device + audio readiness, then the timer
// ---------------------------------------------------------------------------

function InstructionsScreen({
  attempt,
  intro,
}: {
  readonly attempt: PlacementAttempt;
  readonly intro: PlacementIntro;
}) {
  const t = useTranslations("placement.instructions");
  const advance = useAdvancePlacementAttempt(attempt.id);
  const [audioChecked, setAudioChecked] = useState(false);

  return (
    <div className="space-y-5">
      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
          {t("title")}
        </h2>
        <ul className="mt-3 space-y-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          <li>{t("rule1", { minutes: intro.duration_minutes })}</li>
          <li>{t("rule2")}</li>
          <li>{t("rule3")}</li>
          <li>{t("rule4")}</li>
        </ul>
      </div>

      {/* Audio readiness runs before the timer, never during it: a learner must
          not lose exam minutes discovering their headphones are muted. */}
      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="flex items-start gap-3">
          <Headphones
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-[var(--color-text-secondary)]"
            strokeWidth={1.9}
          />
          <div className="flex-1">
            <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
              {t("audioTitle")}
            </h2>
            <p className="mt-1 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {t("audioReason")}
            </p>
            <label className="mt-3 flex cursor-pointer items-center gap-2.5 pointer-coarse:min-h-11">
              <input
                type="checkbox"
                checked={audioChecked}
                onChange={(event) => setAudioChecked(event.target.checked)}
                className="size-4 accent-[var(--color-primary)]"
              />
              <span className="text-[14px] text-[var(--color-text)]">
                {t("audioConfirm")}
              </span>
            </label>
          </div>
        </div>
      </div>

      <StateBanner tone="warning" title={t("timerTitle")} reason={t("timerReason")} />

      <Button
        type="button"
        size="lg"
        onClick={() => advance.mutate("begin")}
        disabled={!audioChecked || advance.isPending}
      >
        {advance.isPending ? t("starting") : t("begin")}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4/5. Pending review, then a released recommendation
// ---------------------------------------------------------------------------

function ResultScreen({
  attemptId,
  intro,
  onRestart,
}: {
  readonly attemptId: string;
  readonly intro: PlacementIntro;
  readonly onRestart: (id: string) => void;
}) {
  const t = useTranslations("placement.result");
  const tRoot = useTranslations("placement");
  const result = usePlacementResult(attemptId);
  const start = useStartPlacementAttempt();

  if (result.isLoading || !result.data) {
    return <Skeleton className="h-48 w-full" />;
  }

  const { released, recommended_course: course, state } = result.data;
  const claimLimit = tRoot("claimLimit");

  if (state === "invalidated") {
    return (
      <StateBanner
        tone="blocked"
        title={t("invalidatedTitle")}
        reason={t("invalidatedReason")}
      />
    );
  }

  // The states the expiry sweep produces. Each needs its own screen: falling
  // through to "your answers are with CLE" would tell a learner who answered
  // nothing, or who never began, that work they did not do is being reviewed.
  if (state === "expired" || state === "abandoned" || state === "technical_review") {
    const canRetry = state !== "technical_review" && intro.attempts_remaining > 0;
    return (
      <div className="space-y-5">
        <StateBanner
          tone={state === "technical_review" ? "waiting" : "warning"}
          title={t(`${state}Title`)}
          reason={t(`${state}Reason`)}
        />
        {canRetry ? (
          <Button
            type="button"
            size="lg"
            onClick={async () => {
              const created = await start.mutateAsync();
              onRestart(created.id);
            }}
            disabled={start.isPending}
          >
            {t("startAgain", { remaining: intro.attempts_remaining })}
          </Button>
        ) : null}
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {claimLimit}
        </p>
      </div>
    );
  }

  if (!released) {
    return (
      <div className="space-y-5">
        <EmptyState
          variant="waiting"
          icon={ClipboardList}
          title={t("pendingTitle")}
          reason={t("pendingReason")}
        />
        <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("whatHappensTitle")}
          </h2>
          <ol className="mt-3 space-y-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
            <li>{t("whatHappens1")}</li>
            <li>{t("whatHappens2")}</li>
            <li>{t("whatHappens3")}</li>
          </ol>
        </div>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {claimLimit}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="flex items-start gap-3">
          <CheckCircle2
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-[var(--color-success)]"
            strokeWidth={1.9}
          />
          <div>
            <p className="text-[13px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-secondary)]">
              {t("releasedEyebrow")}
            </p>
            <h2 className="mt-2 font-display text-[1.75rem] font-semibold text-[var(--color-text)]">
              {course}
            </h2>
            <p className="mt-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {t("releasedReason")}
            </p>
          </div>
        </div>
      </div>

      <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
        {claimLimit}
      </p>

      {intro.attempts_remaining > 0 ? (
        <Button
          type="button"
          variant="outline"
          size="lg"
          onClick={async () => {
            const created = await start.mutateAsync();
            onRestart(created.id);
          }}
          disabled={start.isPending}
        >
          {t("retake", { remaining: intro.attempts_remaining })}
        </Button>
      ) : null}
    </div>
  );
}
