import { describe, expect, it } from "vitest";

import {
  activeCourseId,
  activeCourseKey,
  courseHref,
  courseNavForRole,
  globalNavForRole,
  STUDENT_COURSE_NAV,
  STUDENT_GLOBAL_NAV,
  TEACHER_COURSE_NAV,
  TEACHER_GLOBAL_NAV,
} from "./nav-config";

describe("global rails", () => {
  it("gives the teacher exactly Home, Courses, Calendar, Insights", () => {
    expect(TEACHER_GLOBAL_NAV.map((item) => item.key)).toEqual([
      "home",
      "courses",
      "calendar",
      "insights",
    ]);
  });

  it("gives the student Home, Courses, Calendar, My progress", () => {
    expect(STUDENT_GLOBAL_NAV.map((item) => item.key)).toEqual([
      "home",
      "courses",
      "calendar",
      "myProgress",
    ]);
  });

  it("exposes no global Sessions destination (removal rule 01)", () => {
    for (const nav of [TEACHER_GLOBAL_NAV, STUDENT_GLOBAL_NAV]) {
      expect(nav.some((item) => item.key === "sessions")).toBe(false);
      expect(nav.some((item) => item.href.includes("/sessions"))).toBe(false);
    }
  });

  it("exposes no global Setup destination (removal rule 02)", () => {
    for (const nav of [TEACHER_GLOBAL_NAV, STUDENT_GLOBAL_NAV]) {
      expect(nav.some((item) => item.href.includes("/setup"))).toBe(false);
    }
  });

  it("routes each lane to its own prefix", () => {
    for (const item of TEACHER_GLOBAL_NAV) {
      expect(item.href.startsWith("/teacher/")).toBe(true);
    }
    for (const item of STUDENT_GLOBAL_NAV) {
      expect(item.href.startsWith("/student/")).toBe(true);
    }
  });

  it("has no duplicate hrefs within a lane", () => {
    for (const nav of [TEACHER_GLOBAL_NAV, STUDENT_GLOBAL_NAV]) {
      const hrefs = nav.map((item) => item.href);
      expect(new Set(hrefs).size).toBe(hrefs.length);
    }
  });

  it("selects the rail by role", () => {
    expect(globalNavForRole("instructor")).toBe(TEACHER_GLOBAL_NAV);
    expect(globalNavForRole("student")).toBe(STUDENT_GLOBAL_NAV);
  });
});

describe("course rails", () => {
  it("matches the approved teacher course destinations, in order", () => {
    expect(TEACHER_COURSE_NAV.map((item) => item.key)).toEqual([
      "overview",
      "sessions",
      "materials",
      "activities",
      "practice",
      "students",
      "insights",
    ]);
  });

  it("puts Sessions directly after Overview (Plate 04, rule 2)", () => {
    expect(TEACHER_COURSE_NAV[0].key).toBe("overview");
    expect(TEACHER_COURSE_NAV[1].key).toBe("sessions");
  });

  it("keeps teacher-only management out of the student course rail", () => {
    const studentKeys = STUDENT_COURSE_NAV.map((item) => item.key);
    expect(studentKeys).not.toContain("students");
    expect(studentKeys).toContain("progress");
  });

  it("never exposes Setup as a course destination", () => {
    for (const nav of [TEACHER_COURSE_NAV, STUDENT_COURSE_NAV]) {
      expect(nav.some((item) => item.segment === "setup")).toBe(false);
    }
  });

  it("selects the course rail by role", () => {
    expect(courseNavForRole("instructor")).toBe(TEACHER_COURSE_NAV);
    expect(courseNavForRole("student")).toBe(STUDENT_COURSE_NAV);
  });

  it("builds course-scoped hrefs that always carry the course id", () => {
    for (const item of TEACHER_COURSE_NAV) {
      const href = courseHref("instructor", "abc", item);
      expect(href.startsWith("/teacher/courses/abc")).toBe(true);
    }
    expect(courseHref("instructor", "abc", TEACHER_COURSE_NAV[0])).toBe(
      "/teacher/courses/abc"
    );
    expect(courseHref("student", "abc", STUDENT_COURSE_NAV[1])).toBe(
      "/student/courses/abc/sessions"
    );
  });
});

describe("activeCourseId", () => {
  it("returns null on global destinations", () => {
    expect(activeCourseId("/teacher/dashboard")).toBeNull();
    expect(activeCourseId("/teacher/courses")).toBeNull();
    expect(activeCourseId("/teacher/calendar")).toBeNull();
    expect(activeCourseId("/student/courses")).toBeNull();
  });

  it("returns null for the create form", () => {
    expect(activeCourseId("/teacher/courses/new")).toBeNull();
  });

  it("extracts the id inside a course", () => {
    expect(activeCourseId("/teacher/courses/c1")).toBe("c1");
    expect(activeCourseId("/teacher/courses/c1/sessions/s2")).toBe("c1");
    expect(activeCourseId("/student/courses/c9/practice")).toBe("c9");
    expect(activeCourseId("/dashboard/courses/legacy")).toBe("legacy");
  });
});

describe("activeCourseKey", () => {
  it("lights the destination that owns the route", () => {
    const nav = TEACHER_COURSE_NAV;
    expect(activeCourseKey("/teacher/courses/c1", nav)).toBe("overview");
    expect(activeCourseKey("/teacher/courses/c1/sessions", nav)).toBe("sessions");
    expect(activeCourseKey("/teacher/courses/c1/materials", nav)).toBe(
      "materials"
    );
  });

  it("keeps a sub-route lit on its owning destination (boundary rule 03)", () => {
    const nav = TEACHER_COURSE_NAV;
    // A session detail page is still Sessions.
    expect(activeCourseKey("/teacher/courses/c1/sessions/m1", nav)).toBe(
      "sessions"
    );
    // Schedule is reached from Sessions, not beside it.
    expect(activeCourseKey("/teacher/courses/c1/schedule", nav)).toBe("sessions");
    // Reports and course memory file under Insights (T076–T108).
    expect(activeCourseKey("/teacher/courses/c1/reports", nav)).toBe("insights");
    expect(activeCourseKey("/teacher/courses/c1/memory", nav)).toBe("insights");
    // The legacy enrollment alias resolves to Students.
    expect(activeCourseKey("/teacher/courses/c1/enrollment", nav)).toBe(
      "students"
    );
  });

  it("falls back to overview for an unknown segment", () => {
    expect(
      activeCourseKey("/teacher/courses/c1/unknown", TEACHER_COURSE_NAV)
    ).toBe("overview");
  });
});
