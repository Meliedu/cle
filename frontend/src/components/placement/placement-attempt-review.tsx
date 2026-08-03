"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ChevronLeft, ShieldAlert } from "lucide-react";

import { PageHeader, StateBanner } from "@/components/patterns";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  placementErrorCode,
  usePlacementEvidence,
  useRecordPlacementDecision,
  type PlacementEvidence,
  type PlacementTeacherFlag,
  type PlacementTeacherReview,
} from "@/hooks/use-placement";

import { flagSeverity, hasBlockingFlag, sortFlags } from "./review-flags";

const COURSES = ["LANG1511", "LANG1512", "LANG1513", "LANG1514", "LANG1515"] as const;

/** The order the learner sat the sections in, per the published blueprint. */
const SKILL_ORDER = ["listening", "language_use", "reading"] as const;

/** Blueprint order first, then anything else, so a new skill cannot vanish. */
function orderedSkills(
  scores: Readonly<Record<string, unknown>> | null | undefined
): string[] {
  if (!scores) return [];
  const known = SKILL_ORDER.filter((skill) => skill in scores);
  const rest = Object.keys(scores).filter(
    (skill) => !(SKILL_ORDER as readonly string[]).includes(skill)
  );
  return [...known, ...rest];
}

/** Actions the backend will actually accept from this state. */
type DecisionAction =
  | "approve"
  | "override"
  | "request_advising"
  | "invalidate"
  | "release"
  | "resume_review";

function allowedActions(state: string, blocked: boolean): DecisionAction[] {
  // A blocked attempt cannot be approved away; invalidation is the way out and
  // the server enforces the same rule.
  if (blocked) return ["invalidate"];
  switch (state) {
    case "scored":
    case "review_pending":
      return ["approve", "override", "request_advising", "invalidate"];
    case "technical_review":
      return ["resume_review", "invalidate"];
    case "advising_required":
      return ["approve", "override", "invalidate"];
    case "approved":
    case "overridden":
      return ["release", "invalidate"];
    default:
      return ["invalidate"];
  }
}

/** Actions that need a reason code. Approving and releasing do not. */
function needsReason(action: DecisionAction): boolean {
  return action !== "approve" && action !== "release";
}

/** Actions where a free-text note is genuinely required, not optional. */
function noteRequired(action: DecisionAction): boolean {
  return action === "override" || action === "invalidate";
}

const REASON_CODES = [
  "course_fit",
  "evidence_mismatch",
  "technical_issue",
  "background_evidence",
  "advising_needed",
  "suspected_irregularity",
] as const;

/**
 * The content note on one item, if it has one.
 *
 * A blocking flag means the item carried no defensible key and scored nothing.
 * An advisory one means the content owner revised it and wants the revision
 * confirmed. Those are different asks, so they must not look the same: v1.3
 * ships 22 advisory items and zero blocking ones, and styling all 22 as
 * disputed would teach reviewers to skim past the badge that matters.
 *
 * Severity is resolved server-side from the same set the publication gate uses.
 * A flag stored before that field existed has none, and is treated as blocking:
 * the safe reading of an unknown content defect is the serious one.
 */
export function ItemFlagBadge({
  flags,
  review,
}: {
  readonly flags: readonly PlacementTeacherFlag[];
  readonly review?: PlacementTeacherReview | null;
}) {
  const t = useTranslations("teacher.placement.review");
  if (flags.length === 0) return null;

  const blocking = flags.some((flag) => flag.severity !== "advisory");
  // The review question is the content owner's own wording of what they want
  // checked, which is more use to a reviewer than the flag code behind it.
  const detail = [...flags.map((flag) => flag.detail), review?.review_question]
    .filter(Boolean)
    .join(" · ");

  return (
    <span
      className={cn(
        "ml-2 rounded-[var(--radius-pill)] px-1.5 py-0.5 text-[11px]",
        blocking
          ? "bg-[var(--color-error)]/12 text-[var(--color-error)]"
          : "bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]"
      )}
      // Words, not colour alone, and the detail is reachable without hover.
      title={detail}
    >
      {blocking ? t("itemFlagged") : t("itemAdvisory")}
      <span className="sr-only">{detail ? ` (${detail})` : ""}</span>
    </span>
  );
}

/**
 * The CLE decision surface for one attempt (wireframe T095).
 *
 * Everything a reviewer needs to disagree with the system is on this page:
 * per-band and per-skill evidence, the triggers that fired, the learner's other
 * attempts, and the full per-item answer sheet with keys. The evidence hash is
 * submitted with the decision so a rescore between opening and deciding is
 * rejected rather than silently attributed to the reviewer.
 */
export function PlacementAttemptReview({ attemptId }: { readonly attemptId: string }) {
  const t = useTranslations("teacher.placement.review");
  const evidence = usePlacementEvidence(attemptId);

  if (evidence.isLoading) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-2 sm:px-6" aria-busy="true">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full" />
        <span className="sr-only">{t("loading")}</span>
      </div>
    );
  }

  if (!evidence.data) {
    return (
      <div className="mx-auto w-full max-w-4xl py-2">
        <StateBanner tone="blocked" title={t("notFoundTitle")} reason={t("notFoundReason")} />
      </div>
    );
  }

  return <ReviewBody evidence={evidence.data} />;
}

function ReviewBody({ evidence }: { readonly evidence: PlacementEvidence }) {
  const t = useTranslations("teacher.placement.review");
  const tf = useTranslations("teacher.placement.flag");
  const decide = useRecordPlacementDecision(evidence.attempt_id);

  const [action, setAction] = useState<DecisionAction>("approve");
  const [finalCourse, setFinalCourse] = useState<string>(
    evidence.provisional_course ?? "LANG1511"
  );
  const [reasonCode, setReasonCode] = useState<string>(REASON_CODES[0]);
  const [reasonText, setReasonText] = useState("");
  /** null = no failure; "stale" = evidence moved; otherwise a real error code. */
  const [failure, setFailure] = useState<string | null>(null);

  const flags = useMemo(() => sortFlags(evidence.review_flags), [evidence.review_flags]);
  const blocked = hasBlockingFlag(evidence.review_flags);
  const available = useMemo(
    () => allowedActions(evidence.state, blocked),
    [blocked, evidence.state]
  );

  // Keep the selection legal when the state changes under the reviewer.
  const chosen = available.includes(action) ? action : available[0];
  const decided = ["approved", "overridden", "released", "invalidated"].includes(
    evidence.state
  );

  const submit = useCallback(async () => {
    setFailure(null);
    try {
      await decide.mutateAsync({
        action: chosen,
        final_course: chosen === "override" ? finalCourse : undefined,
        reason_code: chosen === "approve" || chosen === "release" ? undefined : reasonCode,
        reason_text: reasonText || undefined,
        evidence_hash: evidence.evidence_hash,
      });
    } catch (error) {
      // Only a hash mismatch means "reload". Everything else has its own
      // cause, and telling a reviewer to reload for a rejected action sends
      // them round a loop that cannot resolve.
      setFailure(placementErrorCode(error) ?? "unknown");
    }
  }, [chosen, decide, evidence.evidence_hash, finalCourse, reasonCode, reasonText]);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-2 sm:px-6">
      <Link
        href="/teacher/placement"
        className="inline-flex items-center gap-1 text-[14px] font-medium text-[var(--color-text)] underline underline-offset-4 outline-none hover:no-underline focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 pointer-coarse:min-h-11"
      >
        <ChevronLeft aria-hidden="true" className="size-4" />
        {t("backToQueue")}
      </Link>

      <PageHeader
        title={t("title")}
        description={t("subtitle", {
          student: evidence.student_name ?? evidence.student_email ?? t("unknownStudent"),
          form: evidence.form_code,
        })}
      />

      {blocked ? (
        <StateBanner
          tone="blocked"
          title={t("blockedTitle")}
          reason={t("blockedReason")}
        />
      ) : null}

      {/* --- headline evidence --- */}
      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("systemResultTitle")}
          </h2>
          <dl className="mt-3 space-y-2 text-[14px]">
            <Row label={t("provisionalCourse")} value={evidence.provisional_course ?? "—"} />
            <Row
              label={t("sustainedBand")}
              value={
                evidence.highest_sustained_band === null
                  ? "—"
                  : evidence.highest_sustained_band === 0
                    ? t("bandNoneSustained")
                    : t("bandValue", { band: evidence.highest_sustained_band })
              }
            />
            <Row
              label={t("confidence")}
              value={evidence.confidence ? t(`confidenceValue.${evidence.confidence}`) : "—"}
            />
            <Row
              label={t("rawScore")}
              value={
                evidence.raw_score === null
                  ? "—"
                  : evidence.scorable_count !== null &&
                      evidence.scorable_count !== undefined &&
                      evidence.scorable_count < 30
                    ? t("scoreValueReduced", {
                        score: evidence.raw_score,
                        answered: evidence.answered_count ?? 0,
                        scorable: evidence.scorable_count,
                      })
                    : t("scoreValue", {
                        score: evidence.raw_score,
                        answered: evidence.answered_count ?? 0,
                      })
              }
            />
            <Row
              label={t("duration")}
              value={
                evidence.duration_seconds === null
                  ? "—"
                  : evidence.duration_seconds < 60
                    ? t("underAMinute")
                    : t("minutes", {
                        minutes: Math.round(evidence.duration_seconds / 60),
                      })
              }
            />
            <Row
              label={t("boundary")}
              value={
                evidence.clear_next_band_boundary === null
                  ? "—"
                  : t(evidence.clear_next_band_boundary ? "boundaryClear" : "boundaryNarrow")
              }
            />
          </dl>
          <p className="mt-4 text-[12px] text-[var(--color-text-secondary)]">
            {t("versionFootnote", {
              key: evidence.key_version ?? "—",
              rule: evidence.rule_version ?? "—",
            })}
          </p>
        </div>

        <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("skillEvidenceTitle")}
          </h2>
          {/* Blueprint order, not object order. `skill_scores` is stored as
              JSONB, and Postgres reorders JSONB keys by length, so iterating the
              object put Reading first and Language use last -- the opposite of
              the order the learner actually sat them in. */}
          <ul className="mt-3 space-y-3">
            {orderedSkills(evidence.skill_scores).map((skill) => {
              const score = evidence.skill_scores![skill];
              return (
              <li key={skill}>
                <div className="flex items-baseline justify-between">
                  <span className="text-[14px] text-[var(--color-text)]">
                    {t(`skill.${skill}`)}
                  </span>
                  <span className="text-[14px] tabular-nums text-[var(--color-text-secondary)]">
                    {score.correct}/{score.total}
                  </span>
                </div>
                <div
                  className="mt-1.5 h-2 overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={score.total}
                  aria-valuenow={score.correct}
                  aria-label={t("skillProgress", {
                    skill: t(`skill.${skill}`),
                    correct: score.correct,
                    total: score.total,
                  })}
                >
                  <div
                    className="h-full rounded-[var(--radius-pill)] bg-[var(--color-primary)]"
                    style={{ width: `${(score.correct / score.total) * 100}%` }}
                  />
                </div>
              </li>
              );
            })}
          </ul>
        </div>
      </section>

      {/* --- band profile --- */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
          {t("bandProfileTitle")}
        </h2>
        <p className="mt-1 text-[13px] text-[var(--color-text-secondary)]">
          {t("bandProfileReason")}
        </p>
        <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-6">
          {[1, 2, 3, 4, 5, 6].map((band) => {
            const score = evidence.band_scores?.[String(band)] ?? 0;
            const sustained = evidence.highest_sustained_band ?? 0;
            return (
              <li
                key={band}
                className={cn(
                  "rounded-[var(--radius-lg)] border p-3 text-center",
                  band === sustained
                    ? "border-[var(--color-primary)] bg-[var(--color-primary)]/8"
                    : "border-[var(--color-border)]"
                )}
              >
                <p className="text-[12px] uppercase tracking-[0.1em] text-[var(--color-text-secondary)]">
                  {t("bandLabel", { band })}
                </p>
                <p className="mt-1 text-[18px] font-semibold tabular-nums text-[var(--color-text)]">
                  {score}/5
                </p>
              </li>
            );
          })}
        </ul>
        {evidence.lower_band_break ? (
          <p className="mt-3 text-[13px] text-[var(--color-text)]">
            {t("lowerBandBreakNote")}
          </p>
        ) : null}
      </section>

      {/* --- triggers --- */}
      {flags.length > 0 ? (
        <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("flagsTitle")}
          </h2>
          <ul className="mt-3 space-y-2">
            {flags.map((code) => {
              const severity = flagSeverity(code);
              return (
                <li key={code} className="flex items-start gap-2.5">
                  <ShieldAlert
                    aria-hidden="true"
                    className={cn(
                      "mt-0.5 size-4 shrink-0",
                      severity === "blocking"
                        ? "text-[var(--color-error)]"
                        : severity === "review"
                          ? "text-[var(--color-text-secondary)]"
                          : "text-[var(--color-text-secondary)]"
                    )}
                    strokeWidth={1.9}
                  />
                  <div>
                    <p className="text-[14px] font-medium text-[var(--color-text)]">
                      {tf(code)}
                    </p>
                    <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                      {tf(`${code}Detail`)}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {/* --- prior attempts --- */}
      {evidence.prior_attempts.length > 0 ? (
        <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("priorAttemptsTitle")}
          </h2>
          <ul className="mt-3 space-y-2 text-[14px]">
            {evidence.prior_attempts.map((prior) => (
              <li
                key={prior.attempt_id}
                className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-border)] pb-2 last:border-b-0 last:pb-0"
              >
                <span className="text-[var(--color-text)]">
                  {t("priorAttemptLabel", { number: prior.attempt_number })}
                </span>
                <span className="text-[var(--color-text-secondary)]">
                  {t("priorAttemptValue", {
                    course: prior.provisional_course ?? "—",
                    score: prior.raw_score ?? 0,
                    state: prior.state,
                    confidence: prior.confidence
                      ? t(`confidenceValue.${prior.confidence}`)
                      : "—",
                  })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* --- per-item answer sheet --- */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]">
        <h2 className="border-b border-[var(--color-border)] px-5 py-4 text-[15px] font-semibold text-[var(--color-text)]">
          {t("answerSheetTitle")}
        </h2>
        <div
          className="overflow-x-auto"
          tabIndex={0}
          role="region"
          aria-label={t("answerSheetTitle")}
        >
          <table className="w-full min-w-[36rem] text-[14px]">
            <caption className="sr-only">{t("answerSheetCaption")}</caption>
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-[12px] uppercase tracking-[0.1em] text-[var(--color-text-secondary)]">
                <th scope="col" className="px-5 py-2.5">{t("colQuestion")}</th>
                <th scope="col" className="px-3 py-2.5">{t("colBand")}</th>
                <th scope="col" className="px-3 py-2.5">{t("colAnswer")}</th>
                <th scope="col" className="px-3 py-2.5">{t("colKey")}</th>
                <th scope="col" className="px-3 py-2.5">{t("colResult")}</th>
                <th scope="col" className="px-3 py-2.5">{t("colChanges")}</th>
              </tr>
            </thead>
            <tbody>
              {evidence.responses.map((row) => (
                <tr
                  key={row.question_number}
                  className="border-b border-[var(--color-border)] last:border-b-0"
                >
                  <th
                    scope="row"
                    className="px-5 py-2.5 text-left font-normal text-[var(--color-text)]"
                  >
                    {row.question_number}
                    <ItemFlagBadge
                      flags={row.teacher_flags}
                      review={row.teacher_review}
                    />
                  </th>
                  <td className="px-3 py-2.5 tabular-nums text-[var(--color-text-secondary)]">
                    {row.legacy_band}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--color-text)]">
                    {row.response ?? t("noAnswer")}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--color-text-secondary)]">
                    {row.correct_answer}
                  </td>
                  <td className="px-3 py-2.5">
                    {/* Words, not colour alone. */}
                    <span
                      className={
                        row.is_correct
                          ? "text-[var(--color-text)] font-medium"
                          : "text-[var(--color-text-secondary)]"
                      }
                    >
                      {row.is_correct === null
                        ? t("resultUnscored")
                        : row.is_correct
                          ? t("resultCorrect")
                          : t("resultIncorrect")}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-[var(--color-text-secondary)]">
                    {row.change_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* --- decision --- */}
      {decided ? (
        <StateBanner
          tone="success"
          title={t("decidedTitle", { state: t(`state.${evidence.state}`) })}
          reason={t("decidedReason")}
        />
      ) : null}

      {evidence.reviews.length > 0 ? (
        <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {t("decisionsSoFarTitle")}
          </h2>
          <ol className="mt-3 space-y-2 text-[14px]">
            {evidence.reviews.map((review, index) => (
              <li key={index} className="text-[var(--color-text-secondary)]">
                <span className="font-medium text-[var(--color-text)]">
                  {t(`action.${review.action}`)}
                </span>
                {review.final_course ? ` · ${review.final_course}` : ""}
                {review.reason_code ? ` · ${t(`reason.${review.reason_code}`)}` : ""}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
          {t("decisionTitle")}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("decisionReason")}
        </p>

        <fieldset className="mt-4">
          <legend className="text-[13px] font-medium text-[var(--color-text-secondary)]">
            {t("actionLegend")}
          </legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {available.map((option) => (
              <label
                key={option}
                className={cn(
                  "flex cursor-pointer items-start gap-2.5 rounded-[var(--radius-lg)] border p-3",
                  "pointer-coarse:min-h-11 transition-colors duration-150",
                  "focus-within:ring-2 focus-within:ring-[var(--color-primary)]/40",
                  chosen === option
                    ? "border-[var(--color-primary)] bg-[var(--color-primary)]/8"
                    : "border-[var(--color-border)]"
                )}
              >
                <input
                  type="radio"
                  name="placement-action"
                  value={option}
                  checked={chosen === option}
                  onChange={() => setAction(option)}
                  className="mt-0.5 size-4 accent-[var(--color-primary)]"
                />
                <span>
                  <span className="block text-[14px] font-medium text-[var(--color-text)]">
                    {t(`action.${option}`)}
                  </span>
                  <span className="block text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                    {t(`actionHint.${option}`)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {chosen === "override" ? (
          <div className="mt-4">
            <label
              htmlFor="final-course"
              className="text-[13px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("finalCourseLabel")}
            </label>
            <select
              id="final-course"
              value={finalCourse}
              onChange={(event) => setFinalCourse(event.target.value)}
              className="mt-1 block h-11 w-full max-w-xs rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[15px] text-[var(--color-text)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
            >
              {COURSES.map((course) => (
                <option key={course} value={course}>
                  {course}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {needsReason(chosen) ? (
          <div className="mt-4">
            <label
              htmlFor="reason-code"
              className="text-[13px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("reasonCodeLabel")}
            </label>
            <select
              id="reason-code"
              value={reasonCode}
              onChange={(event) => setReasonCode(event.target.value)}
              className="mt-1 block h-11 w-full max-w-sm rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[15px] text-[var(--color-text)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
            >
              {REASON_CODES.map((code) => (
                <option key={code} value={code}>
                  {t(`reason.${code}`)}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        <div className="mt-4">
          <label
            htmlFor="reason-text"
            className="text-[13px] font-medium text-[var(--color-text-secondary)]"
          >
            {noteRequired(chosen) ? t("reasonTextLabelRequired") : t("reasonTextLabel")}
          </label>
          <textarea
            id="reason-text"
            value={reasonText}
            onChange={(event) => setReasonText(event.target.value)}
            rows={3}
            maxLength={2000}
            required={noteRequired(chosen)}
            aria-describedby="reason-text-hint"
            className="mt-1 block w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[15px] leading-relaxed text-[var(--color-text)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
          />
          <p id="reason-text-hint" className="mt-1 text-[12px] text-[var(--color-text-secondary)]">
            {noteRequired(chosen) ? t("reasonTextHintRequired") : t("reasonTextHint")}
          </p>
        </div>

        {failure ? (
          <p className="mt-3 text-[13px] text-[var(--color-error)]" role="alert">
            {failure === "EVIDENCE_STALE"
              ? t("staleEvidence")
              : failure === "RELEASE_NOT_APPROVED"
                ? t("failReleaseNotApproved")
                : failure === "ILLEGAL_TRANSITION"
                  ? t("failIllegalTransition", { state: t(`state.${evidence.state}`) })
                  : failure === "BLOCKED_BY_CONTENT"
                    ? t("failBlockedByContent")
                    : t("failGeneric")}
          </p>
        ) : null}

        <div className="mt-5">
          <Button
            type="button"
            size="lg"
            onClick={submit}
            disabled={
              decide.isPending || (noteRequired(chosen) && !reasonText.trim())
            }
            aria-describedby={blocked ? "blocked-action-hint" : undefined}
          >
            {decide.isPending ? t("recording") : t("record")}
          </Button>
          {blocked ? (
            <p
              id="blocked-action-hint"
              className="mt-2 text-[13px] text-[var(--color-text-secondary)]"
            >
              {t("blockedActionHint")}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-[var(--color-text-secondary)]">{label}</dt>
      <dd className="text-right font-medium text-[var(--color-text)]">{value}</dd>
    </div>
  );
}
