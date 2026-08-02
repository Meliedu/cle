import { describe, expect, it } from "vitest";

import { rollUpByCourse } from "./student-progress";
import type { LearningAction } from "@/lib/learning-path";
import type { StudentWork } from "@/lib/contracts/state";

function action(
  courseId: string,
  work: StudentWork,
  code = "LANG1511",
  name = "LANG1511 · Chinese I"
): LearningAction {
  return {
    item: { id: `${courseId}-${work}-${Math.random()}` } as LearningAction["item"],
    courseId,
    courseCode: code,
    courseName: name,
    work,
    availability: { state: "available", reason: null },
  };
}

// courseTitle's cases live in src/lib/format.test.ts, next to the helper.

describe("rollUpByCourse", () => {
  it("counts submitted and reviewed as done, the rest as outstanding", () => {
    const rows = rollUpByCourse([
      action("c1", "not_started"),
      action("c1", "in_progress"),
      action("c1", "submitted"),
      action("c1", "reviewed"),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].total).toBe(4);
    expect(rows[0].done).toBe(2);
    expect(rows[0].byState.not_started).toBe(1);
    expect(rows[0].byState.reviewed).toBe(1);
  });

  it("orders least-complete first so the course needing attention leads", () => {
    const rows = rollUpByCourse([
      action("done", "reviewed", "AAA100", "AAA100 Finished"),
      action("behind", "not_started", "ZZZ900", "ZZZ900 Behind"),
      action("behind", "not_started", "ZZZ900", "ZZZ900 Behind"),
    ]);
    expect(rows.map((r) => r.courseId)).toEqual(["behind", "done"]);
  });

  it("returns nothing for a learner with no assigned work", () => {
    expect(rollUpByCourse([])).toEqual([]);
  });
});
