import { describe, expect, it } from "vitest";

import type { CourseCalendarEvent } from "@/components/calendar/calendar-types";
import {
  documentReadiness,
  resolveTeachingDay,
  toTeachingEntry,
} from "./teaching-day";

/**
 * "Later today" is the teacher's LOCAL day, so every fixture below is built in
 * local time and then serialised. Authoring them as UTC literals would make the
 * suite pass only in UTC and fail in Hong Kong, where the product runs.
 */
function localAt(day: number, hour: number, minute = 0): string {
  return new Date(2026, 5, day, hour, minute, 0, 0).toISOString();
}

const NOW = new Date(2026, 5, 26, 10, 12, 0, 0);

function meeting(
  id: string,
  at: string,
  overrides: Partial<{ location: string | null; duration: number | null }> = {}
): CourseCalendarEvent {
  return {
    event: {
      id,
      kind: "meeting",
      title: `Session ${id}`,
      at,
      duration_minutes: overrides.duration ?? 50,
      location: overrides.location ?? "Room 2502A",
      status: "planned",
    },
    courseId: "c1",
    courseCode: "LANG1512",
    courseName: "English for Academic Purposes",
    colorIndex: 0,
  };
}

function workItem(
  id: string,
  at: string,
  required: boolean
): CourseCalendarEvent {
  return {
    event: {
      id,
      kind: "work_item",
      title: required ? "Reading notes due" : "Vocabulary quiz release",
      at,
      source_kind: "quiz",
      required,
    },
    courseId: "c2",
    courseCode: "MGMT4240",
    courseName: "Strategic Management",
    colorIndex: 1,
  };
}

describe("toTeachingEntry", () => {
  it("classifies a meeting as a class with venue and duration", () => {
    const entry = toTeachingEntry(meeting("m1", localAt(26, 10, 30)));
    expect(entry.kind).toBe("class");
    expect(entry.location).toBe("Room 2502A");
    expect(entry.durationMinutes).toBe(50);
  });

  it("carries no provenance line for an authored class", () => {
    expect(toTeachingEntry(meeting("m1", localAt(26, 10, 30))).provenance).
      toBeNull();
  });

  it("names the source of an auto-generated entry (Plate 03, rule 3)", () => {
    const release = toTeachingEntry(
      workItem("w1", localAt(26, 18), false)
    );
    const deadline = toTeachingEntry(
      workItem("w2", localAt(26, 23, 59), true)
    );
    expect(release.kind).toBe("generated_release");
    expect(release.provenance).toBe("Auto-added from course setup");
    expect(deadline.kind).toBe("deadline");
    expect(deadline.provenance).toBe("Auto-added from course setup");
  });

  it("keeps ids unique across courses and event kinds", () => {
    const a = toTeachingEntry(meeting("1", localAt(26, 10, 30)));
    const b = toTeachingEntry(workItem("1", localAt(26, 10, 30), false));
    expect(a.id).not.toBe(b.id);
  });
});

describe("resolveTeachingDay", () => {
  it("never ranks a chore above the next class (Plate 01, rule 1)", () => {
    const day = resolveTeachingDay(
      [
        // A deadline lands sooner than the class, but it is still not the job.
        workItem("w1", localAt(26, 10, 15), true),
        meeting("m1", localAt(26, 10, 30)),
      ],
      NOW
    );
    expect(day.next?.entry.kind).toBe("class");
    expect(day.next?.entry.id).toContain("m1");
  });

  it("computes minutes until the next class", () => {
    const day = resolveTeachingDay(
      [meeting("m1", localAt(26, 10, 30))],
      NOW
    );
    expect(day.next?.minutesUntil).toBe(18);
    expect(day.next?.isToday).toBe(true);
    expect(day.next?.inProgress).toBe(false);
  });

  it("keeps a class in progress as the dominant action until it ends", () => {
    // Started 10:00, runs 50 minutes, so 10:12 is mid-lesson.
    const day = resolveTeachingDay(
      [
        meeting("m1", localAt(26, 10)),
        meeting("m2", localAt(26, 14)),
      ],
      NOW
    );
    expect(day.next?.entry.id).toContain("m1");
    expect(day.next?.inProgress).toBe(true);
    expect(day.next?.minutesUntil).toBeLessThan(0);
  });

  it("moves on once the current class has finished", () => {
    // 10-minute class starting at 10:00 has ended by 10:12.
    const day = resolveTeachingDay(
      [
        meeting("m1", localAt(26, 10), { duration: 10 }),
        meeting("m2", localAt(26, 14)),
      ],
      NOW
    );
    expect(day.next?.entry.id).toContain("m2");
  });

  it("lists later-today entries after the hero, same day only", () => {
    const day = resolveTeachingDay(
      [
        meeting("m1", localAt(26, 10, 30)),
        workItem("w1", localAt(26, 18), false),
        workItem("w2", localAt(27, 9), true),
      ],
      NOW
    );
    expect(day.laterToday.map((e) => e.title)).toEqual([
      "Vocabulary quiz release",
    ]);
  });

  it("excludes the hero entry from its own later-today list", () => {
    const day = resolveTeachingDay(
      [meeting("m1", localAt(26, 10, 30))],
      NOW
    );
    expect(day.laterToday).toHaveLength(0);
  });

  it("fills the day rail across day boundaries, bounded", () => {
    const day = resolveTeachingDay(
      [
        meeting("m1", localAt(26, 10, 30)),
        workItem("w1", localAt(26, 18), false),
        workItem("w2", localAt(27, 9), true),
        workItem("w3", localAt(28, 9), true),
        workItem("w4", localAt(29, 9), true),
      ],
      NOW,
      { afterLimit: 3 }
    );
    expect(day.afterThis).toHaveLength(3);
  });

  it("returns a null hero when no class is ahead, keeping context", () => {
    const day = resolveTeachingDay(
      [workItem("w1", localAt(26, 18), false)],
      NOW
    );
    expect(day.next).toBeNull();
    expect(day.laterToday).toHaveLength(1);
    expect(day.afterThis).toHaveLength(1);
  });

  it("drops past entries when there is no class ahead", () => {
    const day = resolveTeachingDay(
      [workItem("w0", localAt(26, 8), true)],
      NOW
    );
    expect(day.next).toBeNull();
    expect(day.laterToday).toHaveLength(0);
  });

  it("is stable regardless of input order", () => {
    const events = [
      workItem("w1", localAt(26, 18), false),
      meeting("m2", localAt(26, 14)),
      meeting("m1", localAt(26, 10, 30)),
    ];
    const forward = resolveTeachingDay(events, NOW);
    const reversed = resolveTeachingDay([...events].reverse(), NOW);
    expect(forward.next?.entry.id).toBe(reversed.next?.entry.id);
    expect(forward.laterToday.map((e) => e.id)).toEqual(
      reversed.laterToday.map((e) => e.id)
    );
  });
});

describe("documentReadiness", () => {
  it("maps 'ready', the value the pipeline actually writes on success", () => {
    // The deployed check constraint is
    //   pending | processing | ready | failed
    // and `pipeline.py` sets 'ready'. Mapping only 'completed' sent every
    // ready source to `idle`, reporting "0 / 7 sources ready" for a course
    // whose sources were all ready.
    expect(documentReadiness("ready")).toBe("ready");
  });

  it("accepts 'completed' as an alias so test fixtures keep working", () => {
    expect(documentReadiness("completed")).toBe("ready");
  });

  it("maps the remaining backend statuses onto the readiness axis", () => {
    expect(documentReadiness("processing")).toBe("processing");
    expect(documentReadiness("pending")).toBe("uploading");
    // A failed parse is recoverable: the file uploaded, so retry/replace exist.
    expect(documentReadiness("failed")).toBe("recoverable_error");
    expect(documentReadiness("something-new")).toBe("idle");
  });

  it("rolls a realistic production source set up correctly", () => {
    // Seven ready + three failed, which is exactly what the dev database
    // holds. Before the fix this produced ready: 0.
    const rollup = [
      ...Array.from({ length: 7 }, () => "ready"),
      ...Array.from({ length: 3 }, () => "failed"),
    ].map(documentReadiness);
    expect(rollup.filter((r) => r === "ready")).toHaveLength(7);
    expect(rollup.filter((r) => r === "recoverable_error")).toHaveLength(3);
    expect(rollup.filter((r) => r === "idle")).toHaveLength(0);
  });
});
