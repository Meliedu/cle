import { describe, expect, it } from "vitest";

import { navForRole, STUDENT_NAV, TEACHER_NAV } from "./nav-config";

describe("navForRole", () => {
  it("returns the teacher lane for instructors", () => {
    expect(navForRole("instructor")).toBe(TEACHER_NAV);
  });

  it("returns the student lane for students", () => {
    expect(navForRole("student")).toBe(STUDENT_NAV);
  });
});

describe("nav configs", () => {
  it("teacher nav has four items pointing at the /teacher tree", () => {
    expect(TEACHER_NAV).toHaveLength(4);
    for (const item of TEACHER_NAV) {
      expect(item.href.startsWith("/teacher/")).toBe(true);
      expect(item.label.length).toBeGreaterThan(0);
    }
  });

  it("student nav has three items pointing at the /student tree", () => {
    expect(STUDENT_NAV).toHaveLength(3);
    for (const item of STUDENT_NAV) {
      expect(item.href.startsWith("/student/")).toBe(true);
      expect(item.label.length).toBeGreaterThan(0);
    }
  });

  it("has no duplicate hrefs within a lane", () => {
    for (const nav of [TEACHER_NAV, STUDENT_NAV]) {
      const hrefs = nav.map((item) => item.href);
      expect(new Set(hrefs).size).toBe(hrefs.length);
    }
  });
});
