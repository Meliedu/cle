import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CourseRowCard } from "./course-row-card";
import type { CourseResponse } from "@/hooks/use-courses";

// The illustration pulls in canvas/seeded rendering we don't need here.
vi.mock("@/components/dashboard/course-illustration", () => ({
  CourseIllustration: () => null,
}));

function makeCourse(overrides: Partial<CourseResponse> = {}): CourseResponse {
  return {
    id: "c1",
    name: "LANG1512",
    code: "LANG1512",
    description: null,
    language: "en",
    semester: "2026 Spring",
    instructor_id: "i1",
    enroll_code: "ABCD2345",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "code",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

afterEach(cleanup);

describe("CourseRowCard", () => {
  it("links to the legacy dashboard workspace by default (student lane)", () => {
    render(<CourseRowCard course={makeCourse()} />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/dashboard/courses/c1?tab=overview");
  });

  it("links to the new teacher course route when an href is supplied", () => {
    render(<CourseRowCard course={makeCourse()} href="/teacher/courses/c1" />);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/teacher/courses/c1");
  });
});
