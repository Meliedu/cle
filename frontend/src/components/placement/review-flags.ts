/**
 * Review-trigger presentation.
 *
 * The backend emits stable machine codes; this maps them to an i18n key and a
 * severity. Codes never reach a screen raw, and the mapping lives here rather
 * than inline so a new backend trigger fails the exhaustiveness check below
 * instead of silently rendering as an unexplained token.
 */

/** Every trigger the scorer can raise (`services/placement_scoring.py`). */
export const REVIEW_FLAG_CODES = [
  "incomplete_answers",
  "duration_too_short",
  "duration_too_long",
  "lower_band_break",
  "declared_background_mismatch",
  "technical_interruption",
  "form_compromised",
  "attempt_spread",
  "response_pattern_anomaly",
  "item_key_disputed",
  "high_band_ceiling",
  "timing_inconsistent",
] as const;

export type ReviewFlagCode = (typeof REVIEW_FLAG_CODES)[number];

/**
 * `blocking` cannot be approved away by a reviewer: the underlying content or
 * form is broken and needs fixing first. `review` needs a judgement call.
 * `advisory` is context a reviewer should read but that does not by itself
 * mean anything is wrong.
 */
export type ReviewFlagSeverity = "blocking" | "review" | "advisory";

export const REVIEW_FLAG_SEVERITY: Readonly<
  Record<ReviewFlagCode, ReviewFlagSeverity>
> = {
  item_key_disputed: "blocking",
  form_compromised: "blocking",
  incomplete_answers: "review",
  duration_too_short: "review",
  duration_too_long: "review",
  lower_band_break: "review",
  declared_background_mismatch: "review",
  technical_interruption: "review",
  attempt_spread: "review",
  response_pattern_anomaly: "review",
  timing_inconsistent: "review",
  high_band_ceiling: "advisory",
};

export function isKnownFlag(code: string): code is ReviewFlagCode {
  return (REVIEW_FLAG_CODES as readonly string[]).includes(code);
}

export function flagSeverity(code: string): ReviewFlagSeverity {
  // An unrecognised code is treated as needing review rather than ignored: a
  // trigger this build does not know about is still a trigger.
  return isKnownFlag(code) ? REVIEW_FLAG_SEVERITY[code] : "review";
}

/** Most serious first, then alphabetical, so the list order is stable. */
const SEVERITY_RANK: Record<ReviewFlagSeverity, number> = {
  blocking: 0,
  review: 1,
  advisory: 2,
};

export function sortFlags(codes: readonly string[]): readonly string[] {
  return [...codes].sort((a, b) => {
    const rank = SEVERITY_RANK[flagSeverity(a)] - SEVERITY_RANK[flagSeverity(b)];
    return rank !== 0 ? rank : a.localeCompare(b);
  });
}

/** True when any flag means the attempt cannot be approved as it stands. */
export function hasBlockingFlag(codes: readonly string[]): boolean {
  return codes.some((code) => flagSeverity(code) === "blocking");
}
