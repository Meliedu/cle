import { describe, expect, it } from "vitest";

import { SETUP_STEP_KEYS, type SetupState } from "@/hooks/use-setup";
import {
  firstIncompleteStage,
  missingStepsForStage,
  SETUP_STAGES,
  stageForStep,
  stageIsReachable,
  stageProgress,
  stageStatuses,
  STAGE_STEPS,
} from "./setup-stages";

function state(overrides: Partial<SetupState> = {}): SetupState {
  const steps: Record<string, boolean> = {};
  for (const key of SETUP_STEP_KEYS) steps[key] = false;
  return {
    setup_status: "draft",
    context_status: "draft",
    steps,
    missing: [...SETUP_STEP_KEYS],
    ...overrides,
  };
}

function withDone(...done: readonly string[]): SetupState {
  const steps: Record<string, boolean> = {};
  for (const key of SETUP_STEP_KEYS) steps[key] = done.includes(key);
  const missing = SETUP_STEP_KEYS.filter((key) => !done.includes(key));
  return { setup_status: "draft", context_status: "draft", steps, missing };
}

describe("the five stages", () => {
  it("are exactly Basics, Sources, Schedule, Review, Publish", () => {
    expect(SETUP_STAGES).toEqual([
      "basics",
      "sources",
      "schedule",
      "review",
      "publish",
    ]);
  });

  it("covers every backend step exactly once (no state identity lost)", () => {
    const mapped = SETUP_STAGES.flatMap((stage) => STAGE_STEPS[stage]);
    expect([...mapped].sort()).toEqual([...SETUP_STEP_KEYS].sort());
    expect(new Set(mapped).size).toBe(mapped.length);
  });

  it("keeps Publish free of step flags: publishing is the action", () => {
    expect(STAGE_STEPS.publish).toEqual([]);
  });

  it("resolves the owning stage for every step", () => {
    expect(stageForStep("basics")).toBe("basics");
    expect(stageForStep("syllabus")).toBe("sources");
    expect(stageForStep("materials")).toBe("sources");
    expect(stageForStep("analyzer_review")).toBe("sources");
    expect(stageForStep("schedule")).toBe("schedule");
    expect(stageForStep("ilo_map")).toBe("review");
    expect(stageForStep("class_code")).toBe("review");
  });
});

describe("stageProgress", () => {
  it("counts sub-steps within a stage", () => {
    const s = withDone("syllabus", "materials");
    expect(stageProgress("sources", s.steps)).toEqual({
      done: 2,
      total: 3,
      complete: false,
    });
  });

  it("marks a stage complete only when every owned step is done", () => {
    const s = withDone("syllabus", "materials", "analyzer_review");
    expect(stageProgress("sources", s.steps).complete).toBe(true);
  });

  it("treats a stage with no owned steps as not complete-by-default", () => {
    expect(stageProgress("publish", {}).complete).toBe(false);
  });
});

describe("firstIncompleteStage", () => {
  it("starts at Basics for a brand-new course", () => {
    expect(firstIncompleteStage(state())).toBe("basics");
    expect(firstIncompleteStage(undefined)).toBe("basics");
  });

  it("advances past a completed stage", () => {
    expect(firstIncompleteStage(withDone("basics"))).toBe("sources");
    expect(
      firstIncompleteStage(withDone("basics", "syllabus", "materials", "analyzer_review"))
    ).toBe("schedule");
  });

  it("lands on Publish once every gating step is done", () => {
    expect(firstIncompleteStage(withDone(...SETUP_STEP_KEYS))).toBe("publish");
  });

  it("lands a published course on its terminal stage", () => {
    const published: SetupState = {
      ...withDone(...SETUP_STEP_KEYS),
      setup_status: "published",
      context_status: "approved",
    };
    expect(firstIncompleteStage(published)).toBe("publish");
  });
});

describe("stageStatuses", () => {
  it("marks exactly one stage as current", () => {
    const statuses = stageStatuses(withDone("basics"), "sources");
    const currents = Object.values(statuses).filter((v) => v === "current");
    expect(currents).toHaveLength(1);
    expect(statuses.sources).toBe("current");
  });

  it("marks earlier finished stages complete", () => {
    const statuses = stageStatuses(withDone("basics"), "sources");
    expect(statuses.basics).toBe("complete");
  });

  it("keeps unfinished later stages pending", () => {
    const statuses = stageStatuses(withDone("basics"), "sources");
    expect(statuses.schedule).toBe("pending");
    expect(statuses.review).toBe("pending");
    expect(statuses.publish).toBe("pending");
  });

  it("does not mark a LATER stage complete when the user navigates back", () => {
    // Everything is done, but the user has gone back to Basics to re-edit it.
    // Review sits ahead of the cursor, so the stepper must read it as pending:
    // the rail is a path, not a scatter of ticks.
    const statuses = stageStatuses(withDone(...SETUP_STEP_KEYS), "basics");
    expect(statuses.basics).toBe("current");
    expect(statuses.sources).toBe("pending");
    expect(statuses.schedule).toBe("pending");
    expect(statuses.review).toBe("pending");
  });

  it("still marks earlier finished stages complete from a later cursor", () => {
    const statuses = stageStatuses(withDone(...SETUP_STEP_KEYS), "review");
    expect(statuses.basics).toBe("complete");
    expect(statuses.sources).toBe("complete");
    expect(statuses.schedule).toBe("complete");
    expect(statuses.review).toBe("current");
  });

  it("marks Publish complete only once the course is published", () => {
    const done = withDone(...SETUP_STEP_KEYS);
    expect(stageStatuses(done, "review").publish).toBe("pending");
    const published: SetupState = {
      ...done,
      setup_status: "published",
      context_status: "approved",
    };
    expect(stageStatuses(published, "review").publish).toBe("complete");
  });
});

describe("stageIsReachable", () => {
  it("opens only Basics for a brand-new course", () => {
    const s = state();
    expect(stageIsReachable("basics", s)).toBe(true);
    expect(stageIsReachable("sources", s)).toBe(false);
    expect(stageIsReachable("review", s)).toBe(false);
  });

  it("opens every stage up to and including the frontier", () => {
    const s = withDone("basics");
    expect(stageIsReachable("basics", s)).toBe(true);
    expect(stageIsReachable("sources", s)).toBe(true);
    expect(stageIsReachable("schedule", s)).toBe(false);
  });

  it("keeps Publish closed while anything is missing", () => {
    const s = withDone("basics", "syllabus", "materials", "analyzer_review", "schedule");
    expect(stageIsReachable("publish", s)).toBe(false);
  });

  it("opens Publish once nothing is missing", () => {
    expect(stageIsReachable("publish", withDone(...SETUP_STEP_KEYS))).toBe(true);
  });

  it("keeps every stage reachable after publication, so setup can be revisited", () => {
    const published: SetupState = {
      ...withDone(...SETUP_STEP_KEYS),
      setup_status: "published",
      context_status: "approved",
    };
    for (const stage of SETUP_STAGES) {
      expect(stageIsReachable(stage, published)).toBe(true);
    }
  });
});

describe("missingStepsForStage", () => {
  it("names what is still outstanding inside a stage", () => {
    expect(missingStepsForStage("sources", withDone("syllabus"))).toEqual([
      "materials",
      "analyzer_review",
    ]);
  });

  it("returns nothing for a finished stage", () => {
    expect(missingStepsForStage("basics", withDone("basics"))).toEqual([]);
  });
});
