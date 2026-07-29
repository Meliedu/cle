/**
 * The student learning path (Student 01 and 02).
 *
 *   Home resolves one recoverable next action with saved progress, source, due
 *   time, and a direct resume action.
 *
 *   Locked, saved, submitted, and reviewed states must survive navigation and
 *   remain understandable without color or animation.
 *
 * Both requirements are about text: every state below carries a sentence that
 * explains it, so nothing depends on a tint or a spinner. Pure, so the
 * resolution rules are testable without a network or a clock.
 */

import type { ChecklistItem, WorkItemStatus } from "@/hooks/use-work-items";
import type {
  Availability,
  AvailabilityState,
  StudentWork,
} from "@/lib/contracts/state";

/** A checklist item resolved into the learner-facing axes, with its course. */
export interface LearningAction {
  readonly item: ChecklistItem;
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseName: string;
  readonly work: StudentWork;
  readonly availability: Availability;
}

/** The course identity a checklist item belongs to. */
export interface CourseIdentity {
  readonly id: string;
  readonly code: string;
  readonly name: string;
}

/**
 * Map the spine's `work_item_progress.status` onto the StudentWork axis.
 *
 * `late` collapses into `submitted` because the learner has done the work; the
 * lateness is a property of the submission, not a different state of progress.
 * `missed` stays `not_started`, and the closed window is expressed through
 * availability instead, so the two facts do not get conflated into one badge.
 */
export function workFromStatus(status: WorkItemStatus): StudentWork {
  switch (status) {
    case "in_progress":
      return "in_progress";
    case "submitted":
    case "late":
      return "submitted";
    case "completed":
    case "follow_up_assigned":
      return "reviewed";
    case "pending":
    case "missed":
      return "not_started";
  }
}

interface AvailabilityCopy {
  /** "Opens Fri, 26 Jun" for a scheduled item. */
  readonly scheduled: (at: string) => string;
  /** "Closed Fri, 26 Jun" for a window that has passed. */
  readonly closed: (at: string) => string;
  /** "Complete step 1" style dependency text. */
  readonly locked: string;
}

/**
 * Resolve when an item is open to the learner, and why.
 *
 * The reason is never optional for a non-available state. That is the whole
 * point of the rule: a locked row that cannot say what unlocks it is
 * indistinguishable from a bug.
 */
export function resolveAvailability(
  item: ChecklistItem,
  now: Date,
  copy: AvailabilityCopy
): Availability {
  const nowMs = now.getTime();

  if (item.visible_from) {
    const opensMs = new Date(item.visible_from).getTime();
    if (opensMs > nowMs) {
      return { state: "scheduled", reason: copy.scheduled(item.visible_from) };
    }
  }

  if (item.close_at) {
    const closesMs = new Date(item.close_at).getTime();
    if (closesMs < nowMs) {
      return { state: "closed", reason: copy.closed(item.close_at) };
    }
  }

  if (item.status === "missed") {
    return {
      state: "closed",
      reason: item.close_at ? copy.closed(item.close_at) : copy.locked,
    };
  }

  return { state: "available", reason: null };
}

/** Rank used to order the learner's work: soonest actionable first. */
function actionRank(action: LearningAction): number {
  if (action.availability.state !== "available") return 3;
  if (action.work === "reviewed" || action.work === "submitted") return 2;
  // Resumable work outranks unstarted work: it is the "recoverable next
  // action" the handoff asks Home to surface.
  return action.work === "in_progress" ? 0 : 1;
}

function dueMs(action: LearningAction): number {
  return action.item.due_at
    ? new Date(action.item.due_at).getTime()
    : Number.POSITIVE_INFINITY;
}

/** Order a learner's work by what they should do next. */
export function orderActions(
  actions: readonly LearningAction[]
): readonly LearningAction[] {
  return [...actions].sort((a, b) => {
    const rank = actionRank(a) - actionRank(b);
    if (rank !== 0) return rank;
    const due = dueMs(a) - dueMs(b);
    if (due !== 0) return due;
    return a.item.title.localeCompare(b.item.title);
  });
}

export interface LearningDay {
  /** The one action Home leads with, or null when there is nothing to do. */
  readonly next: LearningAction | null;
  /** Everything else still open, in the same order. */
  readonly rest: readonly LearningAction[];
}

/**
 * Resolve the single next action.
 *
 * Only genuinely available work can become `next`: a locked or closed item is
 * never presented as something the learner can start, because the resume button
 * would then lie.
 */
export function resolveLearningDay(
  actions: readonly LearningAction[]
): LearningDay {
  const ordered = orderActions(actions);
  const next =
    ordered.find(
      (action) =>
        action.availability.state === "available" &&
        (action.work === "in_progress" || action.work === "not_started")
    ) ?? null;

  return {
    next,
    rest: ordered.filter((action) => action.item.id !== next?.item.id),
  };
}

/**
 * Build actions from a course's checklist.
 *
 * Each item is tagged with its course so a cross-course Home can name where the
 * work lives, which the handoff requires ("source ... remains visible").
 */
export function buildActions(
  course: CourseIdentity,
  items: readonly ChecklistItem[],
  now: Date,
  copy: AvailabilityCopy
): readonly LearningAction[] {
  return items.map((item) => ({
    item,
    courseId: course.id,
    courseCode: course.code,
    courseName: course.name,
    work: workFromStatus(item.status),
    availability: resolveAvailability(item, now, copy),
  }));
}

/** Whether a state must survive a refresh (saved work the learner can lose). */
export function isRecoverable(action: LearningAction): boolean {
  return (
    action.work === "in_progress" && action.availability.state === "available"
  );
}

/** The verb for an action's primary control, as a translation key suffix. */
export function actionVerbKey(action: LearningAction): string {
  if (action.availability.state === "locked") return "locked";
  if (action.availability.state === "scheduled") return "scheduled";
  if (action.availability.state === "closed") return "closed";
  switch (action.work) {
    case "in_progress":
      return "resume";
    case "submitted":
      return "submitted";
    case "reviewed":
      return "viewFeedback";
    case "not_started":
      return "start";
  }
}

/** Availability states that read as "not yet yours to do". */
export const BLOCKED_STATES: readonly AvailabilityState[] = [
  "locked",
  "scheduled",
  "closed",
] as const;
