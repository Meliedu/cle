import { describe, expect, it } from "vitest";

import type { CourseResponse } from "@/hooks/use-courses";
import type { TeachingEntry } from "@/lib/teaching-day";
import {
  buildRoster,
  filterRoster,
  hasActiveFilters,
  statusOptions,
  termOptions,
} from "./course-roster";

function course(
  id: string,
  overrides: Partial<CourseResponse> = {}
): CourseResponse {
  return {
    id,
    name: `Course ${id}`,
    code: id.toUpperCase(),
    description: null,
    language: "english",
    semester: "2026 Spring",
    instructor_id: "u1",
    enroll_code: "ABC",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "open",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as CourseResponse;
}

function nextClass(courseId: string, at: string): TeachingEntry {
  return {
    id: `${courseId}:meeting:x`,
    kind: "class",
    title: "Session 1",
    at,
    courseId,
    courseCode: courseId.toUpperCase(),
    courseName: `Course ${courseId}`,
    colorIndex: 0,
    location: "Room 1",
    durationMinutes: 50,
    provenance: null,
  };
}

describe("buildRoster ordering", () => {
  it("orders by next class, soonest first (actionable chronology)", () => {
    const courses = [course("a"), course("b"), course("c")];
    const map = new Map([
      ["a", nextClass("a", "2026-06-28T10:00:00Z")],
      ["b", nextClass("b", "2026-06-26T10:00:00Z")],
      ["c", nextClass("c", "2026-06-27T10:00:00Z")],
    ]);
    expect(buildRoster(courses, map).map((r) => r.course.id)).toEqual([
      "b",
      "c",
      "a",
    ]);
  });

  it("puts unscheduled active courses after scheduled ones", () => {
    const courses = [course("unscheduled"), course("scheduled")];
    const map = new Map([
      ["scheduled", nextClass("scheduled", "2026-06-26T10:00:00Z")],
    ]);
    expect(buildRoster(courses, map).map((r) => r.course.id)).toEqual([
      "scheduled",
      "unscheduled",
    ]);
  });

  it("sinks archived courses to the bottom even if they have a class", () => {
    const courses = [
      course("archived", { setup_status: "archived" }),
      course("active"),
    ];
    const map = new Map([
      // The archived course has the sooner class, and still sorts last.
      ["archived", nextClass("archived", "2026-06-20T10:00:00Z")],
      ["active", nextClass("active", "2026-06-26T10:00:00Z")],
    ]);
    expect(buildRoster(courses, map).map((r) => r.course.id)).toEqual([
      "active",
      "archived",
    ]);
  });

  it("breaks ties on code so the order is stable", () => {
    const courses = [course("zzz"), course("aaa")];
    expect(buildRoster(courses, new Map()).map((r) => r.course.id)).toEqual([
      "aaa",
      "zzz",
    ]);
  });

  it("changes the verb with status (Plate 02, rule 2)", () => {
    const rows = buildRoster(
      [
        course("published"),
        course("insetup", {
          setup_status: "in_progress",
          context_status: "pending",
        }),
        course("archived", { setup_status: "archived" }),
      ],
      new Map()
    );
    const byId = Object.fromEntries(rows.map((r) => [r.course.id, r.verb]));
    expect(byId.published).toBe("open");
    expect(byId.insetup).toBe("continueSetup");
    expect(byId.archived).toBe("view");
  });

  it("exposes the next session and venue on the row", () => {
    const rows = buildRoster(
      [course("a")],
      new Map([["a", nextClass("a", "2026-06-26T10:00:00Z")]])
    );
    expect(rows[0].nextClass?.location).toBe("Room 1");
    expect(rows[0].nextClass?.title).toBe("Session 1");
  });

  it("leaves nextClass null when nothing is scheduled", () => {
    expect(buildRoster([course("a")], new Map())[0].nextClass).toBeNull();
  });
});

describe("filterRoster", () => {
  const rows = buildRoster(
    [
      course("lang1512", {
        name: "English for Academic Purposes",
        code: "LANG1512",
        semester: "2026 Spring",
      }),
      course("mgmt4240", {
        name: "Strategic Management in China",
        code: "MGMT4240",
        semester: "2026 Spring",
        setup_status: "in_progress",
        context_status: "pending",
      }),
      course("lang2401", {
        name: "Academic Writing",
        code: "LANG2401",
        semester: "2025 Fall",
        setup_status: "archived",
      }),
    ],
    new Map()
  );

  it("matches free text against code, name, and description", () => {
    expect(
      filterRoster(rows, { query: "lang", term: "", status: "" })
    ).toHaveLength(2);
    expect(
      filterRoster(rows, { query: "strategic", term: "", status: "" })
    ).toHaveLength(1);
  });

  it("is case insensitive and trims", () => {
    expect(
      filterRoster(rows, { query: "  MGMT  ", term: "", status: "" })
    ).toHaveLength(1);
  });

  it("filters by term", () => {
    expect(
      filterRoster(rows, { query: "", term: "2025 Fall", status: "" })
    ).toHaveLength(1);
  });

  it("filters by lifecycle", () => {
    expect(
      filterRoster(rows, { query: "", term: "", status: "published" })
    ).toHaveLength(1);
    expect(
      filterRoster(rows, { query: "", term: "", status: "archived" })
    ).toHaveLength(1);
  });

  it("ANDs the three filters", () => {
    expect(
      filterRoster(rows, {
        query: "lang",
        term: "2026 Spring",
        status: "published",
      })
    ).toHaveLength(1);
    expect(
      filterRoster(rows, {
        query: "lang",
        term: "2026 Spring",
        status: "archived",
      })
    ).toHaveLength(0);
  });

  it("returns everything when no filter is set", () => {
    expect(
      filterRoster(rows, { query: "", term: "", status: "" })
    ).toHaveLength(3);
  });
});

describe("filter options", () => {
  it("lists distinct terms, most recent first", () => {
    expect(
      termOptions([
        course("a", { semester: "2025 Fall" }),
        course("b", { semester: "2026 Spring" }),
        course("c", { semester: "2026 Spring" }),
        course("d", { semester: null }),
      ])
    ).toEqual(["2026 Spring", "2025 Fall"]);
  });

  it("lists present lifecycles in canonical, not alphabetical, order", () => {
    const rows = buildRoster(
      [
        course("archived", { setup_status: "archived" }),
        course("published"),
        course("setup", {
          setup_status: "in_progress",
          context_status: "pending",
        }),
      ],
      new Map()
    );
    expect(statusOptions(rows)).toEqual(["published", "setup", "archived"]);
  });

  it("omits lifecycles that are not on the roster", () => {
    const rows = buildRoster([course("published")], new Map());
    expect(statusOptions(rows)).toEqual(["published"]);
  });
});

describe("hasActiveFilters", () => {
  it("is false only when every filter is empty", () => {
    expect(hasActiveFilters({ query: "", term: "", status: "" })).toBe(false);
    expect(hasActiveFilters({ query: "a", term: "", status: "" })).toBe(true);
    expect(hasActiveFilters({ query: "", term: "t", status: "" })).toBe(true);
    expect(hasActiveFilters({ query: "", term: "", status: "s" })).toBe(true);
  });
});
