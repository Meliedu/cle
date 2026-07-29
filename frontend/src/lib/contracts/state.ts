/**
 * The state and data contract from the approved UI/UX handoff (22 July 2026).
 *
 * The handoff separates four things the product had previously conflated:
 * lifecycle, readiness, visibility, and learner work. Each axis below is one
 * authoritative owner. Nothing in the UI may infer an axis from a badge string,
 * a URL segment, or a duplicated local boolean. Call the derivation helpers
 * here instead so every surface reads the same value.
 *
 * Release rule the axes exist to serve: "each lifecycle or readiness value has
 * one authoritative state owner" (component boundary rule 01).
 */

// ---------------------------------------------------------------------------
// CourseLifecycle
// ---------------------------------------------------------------------------

/**
 * Controls Setup availability, the course action verb, and edit/access
 * affordances. `setup` is the transient authoring stage; once `published`,
 * configuration is reached contextually from Overview and Setup stops being a
 * destination at all.
 */
export type CourseLifecycle = "draft" | "setup" | "published" | "archived";

export const COURSE_LIFECYCLES: readonly CourseLifecycle[] = [
  "draft",
  "setup",
  "published",
  "archived",
] as const;

/** The subset of a course row the lifecycle derivation depends on. */
export interface LifecycleSource {
  readonly setup_status?: string | null;
  readonly context_status?: string | null;
  readonly archived_at?: string | null;
  readonly setup_checklist?: Record<string, boolean> | null;
}

/**
 * Single derivation of lifecycle from the server row.
 *
 * `published` requires BOTH `setup_status === "published"` and an approved
 * context. That is the pre-existing `isCoursePublished` rule, kept verbatim so the
 * roster verb and the overview badge can never disagree. A course that has
 * started its checklist reads `setup`; an untouched one reads `draft`. That
 * distinction is what lets Setup be transient: `draft`/`setup` expose it,
 * `published`/`archived` never do.
 */
export function courseLifecycle(course: LifecycleSource): CourseLifecycle {
  if (course.archived_at) return "archived";
  if (course.setup_status === "archived") return "archived";
  if (course.setup_status === "published" && course.context_status === "approved") {
    return "published";
  }
  const checklist = course.setup_checklist ?? {};
  const started = Object.values(checklist).some(Boolean);
  return started || course.setup_status === "in_progress" ? "setup" : "draft";
}

/** Lifecycle gates whether Setup is a reachable destination at all. */
export function setupIsAvailable(lifecycle: CourseLifecycle): boolean {
  return lifecycle === "draft" || lifecycle === "setup";
}

/**
 * Status must change the verb (Plate 02, rule 2). One mapping, so the roster
 * row, the dashboard card, and any future surface all say the same thing.
 */
export type CourseActionVerb = "open" | "continueSetup" | "view";

export function courseActionVerb(lifecycle: CourseLifecycle): CourseActionVerb {
  switch (lifecycle) {
    case "published":
      return "open";
    case "draft":
    case "setup":
      return "continueSetup";
    case "archived":
      return "view";
  }
}

// ---------------------------------------------------------------------------
// SourceReadiness
// ---------------------------------------------------------------------------

/**
 * Controls source status, progress, recovery action, and publish readiness.
 *
 * The two error states are deliberately distinct: a `recoverable_error` keeps
 * the route and every accepted file intact and offers Retry/Replace, while a
 * `blocking_error` cannot be retried into success and needs the source removed
 * or replaced before publish can proceed.
 */
export type SourceReadiness =
  | "idle"
  | "uploading"
  | "processing"
  | "ready"
  | "recoverable_error"
  | "blocking_error";

export const SOURCE_READINESS_VALUES: readonly SourceReadiness[] = [
  "idle",
  "uploading",
  "processing",
  "ready",
  "recoverable_error",
  "blocking_error",
] as const;

/** A source is still moving; the UI shows progress and suppresses publish. */
export function sourceIsInFlight(readiness: SourceReadiness): boolean {
  return readiness === "uploading" || readiness === "processing";
}

/** Only a recoverable failure offers Retry parsing. */
export function sourceIsRetryable(readiness: SourceReadiness): boolean {
  return readiness === "recoverable_error";
}

export function sourceNeedsAttention(readiness: SourceReadiness): boolean {
  return readiness === "recoverable_error" || readiness === "blocking_error";
}

/**
 * Publish readiness derived from the whole source set. A single blocking error
 * stops publish; in-flight work only defers it.
 */
export interface SourceRollup {
  readonly total: number;
  readonly ready: number;
  readonly inFlight: number;
  readonly needsAttention: number;
  readonly blocking: number;
}

export function rollUpSources(
  readinesses: readonly SourceReadiness[]
): SourceRollup {
  return readinesses.reduce<SourceRollup>(
    (acc, value) => ({
      total: acc.total + 1,
      ready: acc.ready + (value === "ready" ? 1 : 0),
      inFlight: acc.inFlight + (sourceIsInFlight(value) ? 1 : 0),
      needsAttention: acc.needsAttention + (sourceNeedsAttention(value) ? 1 : 0),
      blocking: acc.blocking + (value === "blocking_error" ? 1 : 0),
    }),
    { total: 0, ready: 0, inFlight: 0, needsAttention: 0, blocking: 0 }
  );
}

// ---------------------------------------------------------------------------
// SessionReadiness
// ---------------------------------------------------------------------------

/** Controls the Prepare / Open / Monitor / Close / Review verbs. */
export type SessionReadiness =
  | "draft"
  | "needs_review"
  | "ready"
  | "live"
  | "closed";

export const SESSION_READINESS_VALUES: readonly SessionReadiness[] = [
  "draft",
  "needs_review",
  "ready",
  "live",
  "closed",
] as const;

export type SessionActionVerb =
  | "prepare"
  | "review"
  | "open"
  | "monitor"
  | "close";

/**
 * One authoritative session state machine (no duplicated local booleans).
 * `needs_review` gets `review`, not `prepare`, so the instructor is sent to the
 * thing that is actually blocking readiness.
 */
export function sessionActionVerb(readiness: SessionReadiness): SessionActionVerb {
  switch (readiness) {
    case "draft":
      return "prepare";
    case "needs_review":
      return "review";
    case "ready":
      return "open";
    case "live":
      return "monitor";
    case "closed":
      return "close";
  }
}

/** Legal transitions, used by the guard below and by its unit tests. */
const SESSION_TRANSITIONS: Record<SessionReadiness, readonly SessionReadiness[]> = {
  draft: ["needs_review", "ready"],
  needs_review: ["draft", "ready"],
  ready: ["needs_review", "live", "closed"],
  live: ["closed"],
  closed: [],
};

export function canTransitionSession(
  from: SessionReadiness,
  to: SessionReadiness
): boolean {
  return SESSION_TRANSITIONS[from].includes(to);
}

// ---------------------------------------------------------------------------
// Visibility
// ---------------------------------------------------------------------------

/**
 * Controls learner availability without changing authoring readiness.
 *
 * The handoff is explicit that these are orthogonal: "Publishing a course never
 * silently opens student access." Visibility is therefore never derived from
 * lifecycle; it is its own stored value.
 */
export type Visibility = "hidden" | "scheduled" | "open" | "closed";

export const VISIBILITY_VALUES: readonly Visibility[] = [
  "hidden",
  "scheduled",
  "open",
  "closed",
] as const;

export function learnerCanSee(visibility: Visibility): boolean {
  return visibility === "open" || visibility === "closed";
}

export function learnerCanWork(visibility: Visibility): boolean {
  return visibility === "open";
}

// ---------------------------------------------------------------------------
// StudentWork
// ---------------------------------------------------------------------------

/** Controls Start / Resume / Submitted / View feedback and progress recovery. */
export type StudentWork =
  | "not_started"
  | "in_progress"
  | "submitted"
  | "reviewed";

export const STUDENT_WORK_VALUES: readonly StudentWork[] = [
  "not_started",
  "in_progress",
  "submitted",
  "reviewed",
] as const;

export type StudentWorkVerb = "start" | "resume" | "submitted" | "viewFeedback";

export function studentWorkVerb(work: StudentWork): StudentWorkVerb {
  switch (work) {
    case "not_started":
      return "start";
    case "in_progress":
      return "resume";
    case "submitted":
      return "submitted";
    case "reviewed":
      return "viewFeedback";
  }
}

/** Work that must survive refresh and back navigation. */
export function workIsRecoverable(work: StudentWork): boolean {
  return work === "in_progress";
}

// ---------------------------------------------------------------------------
// ReviewState
// ---------------------------------------------------------------------------

/** Controls instructor review cues and provenance confidence. */
export type ReviewState = "unreviewed" | "accepted" | "needs_change";

export const REVIEW_STATE_VALUES: readonly ReviewState[] = [
  "unreviewed",
  "accepted",
  "needs_change",
] as const;

/**
 * Provenance a generated or reviewed artifact carries with it (boundary rule
 * 04, "one trace"). Every field is required at the type level so a generated
 * object cannot be rendered without its origin.
 */
export interface Provenance {
  readonly sourceId: string;
  readonly sourceLabel: string;
  /** Page, section, or timestamp inside the source. */
  readonly locator: string | null;
  readonly reviewState: ReviewState;
  readonly reviewerName: string | null;
  readonly reviewedAt: string | null;
}

// ---------------------------------------------------------------------------
// Availability (learner-facing sequence items)
// ---------------------------------------------------------------------------

/**
 * Why a sequence item is or is not open to a learner. The handoff requires the
 * unlock reason to be readable as text, never color-only, so this carries the
 * dependency alongside the state.
 */
export type AvailabilityState = "available" | "locked" | "scheduled" | "closed";

export interface Availability {
  readonly state: AvailabilityState;
  /**
   * Plain-language reason shown next to the item, e.g. "Complete step 1" or
   * "Opens after class". Required for every non-available state.
   */
  readonly reason: string | null;
}

export function isLocked(availability: Availability): boolean {
  return availability.state === "locked";
}
