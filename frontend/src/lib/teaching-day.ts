/**
 * The teaching-day model.
 *
 * Plate 01 requires the dashboard to resolve exactly ONE next teaching action
 * and to render its day agenda from the SAME event model the Calendar owns:
 *
 *   Share the same event model; dashboard renders contextual read-only agenda,
 *   not a second calendar editor.
 *
 * Everything here is pure, so the resolution rules are unit-testable without a
 * network or a clock. The hook layer (`use-teaching-day`) supplies the events.
 */

import type { CourseCalendarEvent } from "@/components/calendar/calendar-types";
import type { SourceReadiness } from "@/lib/contracts/state";

/** How an agenda entry should be labelled and acted on. */
export type TeachingEntryKind =
  | "class"
  | "generated_release"
  | "deadline"
  | "assignment";

/**
 * One entry in a teaching agenda. Every field the handoff requires to be
 * available as TEXT is a field here (type, title, time, course, provenance)
 * so color can stay supplementary (Plate 03, rule 2).
 */
export interface TeachingEntry {
  readonly id: string;
  readonly kind: TeachingEntryKind;
  readonly title: string;
  readonly at: string;
  readonly courseId: string;
  readonly courseCode: string;
  readonly courseName: string;
  readonly colorIndex: number;
  /** Room, "Online", or null when the event carries no venue. */
  readonly location: string | null;
  readonly durationMinutes: number | null;
  /**
   * Where this entry came from, as text. Auto-generated entries must identify
   * their source (Plate 03, rule 3), so this is non-null for them.
   */
  readonly provenance: string | null;
}

/** The single dominant action the dashboard hero renders. */
export interface NextTeachingAction {
  readonly entry: TeachingEntry;
  /** Whole minutes until start; negative once the class has begun. */
  readonly minutesUntil: number;
  readonly isToday: boolean;
  /** True between start and start + duration. */
  readonly inProgress: boolean;
}

/** Everything the dashboard needs, derived once from the shared feed. */
export interface TeachingDay {
  readonly next: NextTeachingAction | null;
  /** Entries after `next` that fall on the same calendar day. */
  readonly laterToday: readonly TeachingEntry[];
  /** The next few entries after `next`, regardless of day, for the day rail. */
  readonly afterThis: readonly TeachingEntry[];
}

const MS_PER_MINUTE = 60_000;

function sameCalendarDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * Provenance sentence for an auto-generated entry.
 *
 * The Calendar plate shows "Auto-added from course setup" beneath generated
 * releases and deadlines, so an instructor can tell what they scheduled from
 * what the setup rules produced. Classes are authored directly and carry no
 * provenance line.
 */
function provenanceFor(kind: TeachingEntryKind): string | null {
  switch (kind) {
    case "generated_release":
    case "deadline":
      return "Auto-added from course setup";
    case "assignment":
      return "Synced from Canvas";
    case "class":
      return null;
  }
}

/**
 * Classify a raw feed event.
 *
 * `work_item` events are the ones course setup generates. A work item with a
 * hard due date reads as a deadline; one that simply becomes available reads as
 * a release. That distinction is what lets the agenda say "Vocabulary quiz
 * release" and "Reading notes due" rather than two identical rows.
 */
export function toTeachingEntry(tagged: CourseCalendarEvent): TeachingEntry {
  const { event } = tagged;

  let kind: TeachingEntryKind;
  let location: string | null = null;
  let durationMinutes: number | null = null;

  if (event.kind === "meeting") {
    kind = "class";
    location = event.location;
    durationMinutes = event.duration_minutes;
  } else if (event.kind === "assignment") {
    kind = "assignment";
  } else {
    kind = event.required ? "deadline" : "generated_release";
  }

  return {
    id: `${tagged.courseId}:${event.kind}:${event.id}`,
    kind,
    title: event.title,
    at: event.at,
    courseId: tagged.courseId,
    courseCode: tagged.courseCode,
    courseName: tagged.courseName,
    colorIndex: tagged.colorIndex,
    location,
    durationMinutes,
    provenance: provenanceFor(kind),
  };
}

interface ResolveOptions {
  /** How many entries the day rail shows after the current one. */
  readonly afterLimit?: number;
}

/**
 * Resolve the one next teaching action plus its surrounding agenda.
 *
 * "Never rank local chores above the next class" (Plate 01, rule 1) is
 * implemented literally: only a `class` entry can become `next`. Releases and
 * deadlines are context, never the dominant object.
 *
 * A class already under way still wins until it ends: an instructor mid-lesson
 * needs the room they are standing in, not the one after it.
 */
export function resolveTeachingDay(
  tagged: readonly CourseCalendarEvent[],
  now: Date,
  options: ResolveOptions = {}
): TeachingDay {
  const afterLimit = options.afterLimit ?? 3;

  const entries = tagged
    .map(toTeachingEntry)
    .sort((a, b) => a.at.localeCompare(b.at));

  const nowMs = now.getTime();

  const nextEntry =
    entries.find((entry) => {
      if (entry.kind !== "class") return false;
      const startMs = new Date(entry.at).getTime();
      const endMs = startMs + (entry.durationMinutes ?? 0) * MS_PER_MINUTE;
      return endMs >= nowMs;
    }) ?? null;

  if (!nextEntry) {
    // No class ahead. Everything still in the future is context only.
    const upcoming = entries.filter(
      (entry) => new Date(entry.at).getTime() >= nowMs
    );
    return {
      next: null,
      laterToday: upcoming.filter((entry) =>
        sameCalendarDay(new Date(entry.at), now)
      ),
      afterThis: upcoming.slice(0, afterLimit),
    };
  }

  const startMs = new Date(nextEntry.at).getTime();
  const endMs = startMs + (nextEntry.durationMinutes ?? 0) * MS_PER_MINUTE;

  const next: NextTeachingAction = {
    entry: nextEntry,
    minutesUntil: Math.round((startMs - nowMs) / MS_PER_MINUTE),
    isToday: sameCalendarDay(new Date(nextEntry.at), now),
    inProgress: startMs <= nowMs && nowMs <= endMs,
  };

  const rest = entries.filter(
    (entry) => entry.id !== nextEntry.id && new Date(entry.at).getTime() >= startMs
  );

  return {
    next,
    laterToday: rest.filter((entry) =>
      sameCalendarDay(new Date(entry.at), new Date(nextEntry.at))
    ),
    afterThis: rest.slice(0, afterLimit),
  };
}

/**
 * Human sentence for the hero eyebrow.
 *
 * Deliberately not a live-ticking countdown: the release contract requires
 * status to be readable under reduced motion and announced without moving
 * focus, and a per-second timer is neither.
 */
export function describeLead(next: NextTeachingAction): {
  readonly key: string;
  readonly values: Record<string, string | number>;
} {
  if (next.inProgress) return { key: "inProgress", values: {} };
  const minutes = next.minutesUntil;
  if (minutes <= 60) return { key: "inMinutes", values: { minutes } };
  if (next.isToday) return { key: "todayAt", values: { time: next.entry.at } };
  return { key: "onDay", values: { at: next.entry.at } };
}

// ---------------------------------------------------------------------------
// Source readiness
// ---------------------------------------------------------------------------

/**
 * Map a `documents.status` row onto the SourceReadiness axis.
 *
 * The terminal success value is `ready`: that is what the check constraint in
 * the database allows and what `pipeline.py` actually writes. `completed` is
 * accepted as an alias because the SQLAlchemy model's own constraint still
 * lists it, so `Base.metadata.create_all` (used to build the test database)
 * produces rows with that value. Both mean the same thing to a user, and
 * accepting both is what keeps this correct in production AND under test.
 *
 * Getting this wrong is not cosmetic: an unmapped value falls through to
 * `idle`, which would report "0 / 7 sources ready" for a course whose sources
 * are all ready, on the dashboard hero, the course overview, and the setup
 * provenance rail at once.
 *
 * `failed` maps to the recoverable state because the recovery path (retry
 * parsing, or replace the file) always exists for a document that uploaded.
 */
export function documentReadiness(status: string): SourceReadiness {
  switch (status) {
    case "ready":
    case "completed":
      return "ready";
    case "processing":
      return "processing";
    case "pending":
      return "uploading";
    case "failed":
      return "recoverable_error";
    default:
      return "idle";
  }
}
