import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  STUDENT_COURSE_NAV,
  STUDENT_GLOBAL_NAV,
  TEACHER_COURSE_NAV,
  TEACHER_GLOBAL_NAV,
  activeCourseId,
  isSetupRoute,
} from "@/components/layout/nav-config";

/**
 * The final release checklist, as an executable guard.
 *
 *   [ ] No global Sessions, permanent Setup, rail Collapse preference,
 *       duplicate horizontal course tabs, or Before/In/After rail buckets.
 *
 * These are things the approved handoff removes ("Explicitly remove from the
 * implementation"). A unit test on the nav config alone would not catch a
 * regression that reintroduces them somewhere else, so this also scans the
 * layout source for the specific patterns that carried them.
 */

const SRC = path.resolve(__dirname, "..");

function walk(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === "__tests__") continue;
      walk(full, acc);
    } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      acc.push(full);
    }
  }
  return acc;
}

const SOURCE_FILES = walk(SRC);

function read(relative: string): string {
  return readFileSync(path.join(SRC, relative), "utf8");
}

describe("removal rule 01: no global Sessions destination", () => {
  it("keeps Sessions out of both global rails", () => {
    for (const nav of [TEACHER_GLOBAL_NAV, STUDENT_GLOBAL_NAV]) {
      expect(nav.some((item) => /sessions/i.test(item.href))).toBe(false);
      expect(nav.some((item) => /sessions/i.test(item.key))).toBe(false);
    }
  });

  it("gives Sessions a course-scoped route in both course rails", () => {
    for (const nav of [TEACHER_COURSE_NAV, STUDENT_COURSE_NAV]) {
      const sessions = nav.find((item) => item.key === "sessions");
      expect(sessions).toBeTruthy();
      expect(sessions?.segment).toBe("sessions");
    }
  });

  it("has no top-level /sessions route in the app tree", () => {
    const sessionRoutes = SOURCE_FILES.filter((file) =>
      /[/\\](teacher|student)[/\\]sessions[/\\]/.test(file)
    );
    expect(sessionRoutes).toEqual([]);
  });
});

describe("removal rule 02: Setup is transient, never a standing destination", () => {
  it("appears in no rail, global or course", () => {
    for (const nav of [TEACHER_GLOBAL_NAV, STUDENT_GLOBAL_NAV]) {
      expect(nav.some((item) => /setup/i.test(item.href))).toBe(false);
    }
    for (const nav of [TEACHER_COURSE_NAV, STUDENT_COURSE_NAV]) {
      expect(nav.some((item) => item.segment === "setup")).toBe(false);
    }
  });
});

describe("removal rule 03: no Collapse preference", () => {
  it("stores no rail width or collapse flag anywhere", () => {
    const offenders = SOURCE_FILES.filter((file) => {
      const source = readFileSync(file, "utf8");
      return /sidebar\.collapsed|rail\.collapsed|RAIL_COLLAPSED_KEY/.test(source);
    });
    expect(offenders).toEqual([]);
  });

  it("exposes no collapse control in the sidebar", () => {
    const sidebar = read("components/layout/sidebar.tsx");
    expect(sidebar).not.toMatch(/Collapse sidebar|Expand sidebar|ChevronsLeft/);
    // The rail is a single fixed width, per the component contract.
    expect(sidebar).toMatch(/RAIL_WIDTH\s*=\s*224/);
  });
});

describe("removal rule 04: no Before/In/After Class buckets", () => {
  it("groups no course destination by time of day", () => {
    const offenders = SOURCE_FILES.filter((file) => {
      const source = readFileSync(file, "utf8");
      return /["'`](Before Class|In Class|After Class)["'`]/.test(source);
    });
    expect(offenders).toEqual([]);
  });

  it("renders the course rail as one flat list", () => {
    const railSource = read("components/layout/sidebar-section-nav.tsx");
    expect(railSource).not.toMatch(/SECTION_GROUPS|group\.label/);
  });
});

describe("removal rule 05: no second horizontal course tab row", () => {
  it("renders no tab nav in the course workspace shell", () => {
    const shell = read("components/course/course-workspace-shell.tsx");
    // The rail is the only course navigation system.
    expect(shell).not.toMatch(/aria-current=\{isActive \? "page"/);
    expect(shell).not.toMatch(/TABS\s*:/);
    expect(shell).not.toMatch(/overflow-x-auto border-b/);
  });

  it("keeps exactly one breadcrumb nav in the shell", () => {
    const shell = read("components/course/course-workspace-shell.tsx");
    const navCount = (shell.match(/<nav\b/g) ?? []).length;
    expect(navCount).toBe(1);
  });

  it("renders no breadcrumb trail in the global top bar", () => {
    // Location belongs to the page header; the top bar carrying its own
    // trail was the duplicate-navigation pattern the handoff removes.
    const navbar = read("components/layout/navbar.tsx");
    expect(navbar).not.toMatch(/Breadcrumb|useBreadcrumbs|SEGMENT_LABELS/);
  });
});

describe("removal rule 06: no raw backend errors in user copy", () => {
  it("routes every failure surface through the safe-error contract", () => {
    // The setup source list is the surface that leaked. It must not be able
    // to read a message off an API payload at all.
    const list = read("components/setup/source-status-list.tsx");
    expect(list).toMatch(/safeErrorFromCode/);
    expect(list).not.toMatch(/error_message|\.detail\b/);
  });
});

describe("course navigation renders only after course entry", () => {
  it("yields no course id on a global route", () => {
    expect(activeCourseId("/teacher/dashboard")).toBeNull();
    expect(activeCourseId("/teacher/courses")).toBeNull();
    expect(activeCourseId("/student/calendar")).toBeNull();
  });

  it("suppresses the course rail inside setup (Plate 05, rule 2)", () => {
    expect(isSetupRoute("/teacher/courses/c1/setup")).toBe(true);
    expect(isSetupRoute("/teacher/courses/c1/setup?stage=sources")).toBe(true);
    expect(activeCourseId("/teacher/courses/c1/setup")).toBeNull();
    // A normal course route still renders the rail.
    expect(isSetupRoute("/teacher/courses/c1/sessions")).toBe(false);
    expect(activeCourseId("/teacher/courses/c1/sessions")).toBe("c1");
  });
});

describe("session routes always carry course context", () => {
  it("has no session route outside a course directory", () => {
    const sessionFiles = SOURCE_FILES.filter((file) =>
      /[/\\]sessions[/\\]/.test(file)
    );
    expect(sessionFiles.length).toBeGreaterThan(0);
    for (const file of sessionFiles) {
      expect(file).toMatch(/courses[/\\]\[courseId\][/\\]sessions/);
    }
  });
});
