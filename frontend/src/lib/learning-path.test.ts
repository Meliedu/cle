import { describe, expect, it } from "vitest";

import type { ChecklistItem, WorkItemStatus } from "@/hooks/use-work-items";
import {
  actionVerbKey,
  buildActions,
  isRecoverable,
  orderActions,
  resolveAvailability,
  resolveLearningDay,
  workFromStatus,
  type LearningAction,
} from "./learning-path";

const NOW = new Date(2026, 5, 26, 12, 0);

const COPY = {
  scheduled: (at: string) => `Opens ${new Date(at).getDate()} Jun`,
  closed: (at: string) => `Closed ${new Date(at).getDate()} Jun`,
  locked: "Complete the earlier step",
};

const COURSE = { id: "c1", code: "LANG1512", name: "Academic English" };

function item(overrides: Partial<ChecklistItem> = {}): ChecklistItem {
  return {
    id: "w1",
    course_id: "c1",
    source_kind: "checkpoint",
    source_id: "cp1",
    title: "Session 4 checkpoint",
    required: true,
    score_bearing: false,
    due_at: new Date(2026, 5, 26, 16, 20).toISOString(),
    close_at: null,
    visible_from: null,
    status: "in_progress",
    ...overrides,
  };
}

function action(overrides: Partial<ChecklistItem> = {}): LearningAction {
  return buildActions(COURSE, [item(overrides)], NOW, COPY)[0];
}

describe("workFromStatus", () => {
  it("maps every spine status onto the StudentWork axis", () => {
    const cases: Array<[WorkItemStatus, string]> = [
      ["pending", "not_started"],
      ["in_progress", "in_progress"],
      ["submitted", "submitted"],
      ["late", "submitted"],
      ["completed", "reviewed"],
      ["follow_up_assigned", "reviewed"],
      ["missed", "not_started"],
    ];
    for (const [status, expected] of cases) {
      expect(workFromStatus(status)).toBe(expected);
    }
  });

  it("keeps lateness out of the progress axis", () => {
    // A late submission is still submitted work; lateness belongs to the
    // submission, not to how far the learner got.
    expect(workFromStatus("late")).toBe(workFromStatus("submitted"));
  });
});

describe("resolveAvailability", () => {
  it("is available with no reason when the window is open", () => {
    const result = resolveAvailability(item(), NOW, COPY);
    expect(result.state).toBe("available");
    expect(result.reason).toBeNull();
  });

  it("explains a future opening date", () => {
    const result = resolveAvailability(
      item({ visible_from: new Date(2026, 5, 28).toISOString() }),
      NOW,
      COPY
    );
    expect(result.state).toBe("scheduled");
    expect(result.reason).toBe("Opens 28 Jun");
  });

  it("explains a closed window", () => {
    const result = resolveAvailability(
      item({ close_at: new Date(2026, 5, 24).toISOString() }),
      NOW,
      COPY
    );
    expect(result.state).toBe("closed");
    expect(result.reason).toBe("Closed 24 Jun");
  });

  it("gives every blocked state a reason, never a bare state", () => {
    const blocked = [
      resolveAvailability(
        item({ visible_from: new Date(2026, 5, 28).toISOString() }),
        NOW,
        COPY
      ),
      resolveAvailability(
        item({ close_at: new Date(2026, 5, 24).toISOString() }),
        NOW,
        COPY
      ),
      resolveAvailability(item({ status: "missed" }), NOW, COPY),
    ];
    for (const result of blocked) {
      expect(result.state).not.toBe("available");
      expect(result.reason).toBeTruthy();
    }
  });

  it("treats a missed item as closed, not as available work", () => {
    expect(resolveAvailability(item({ status: "missed" }), NOW, COPY).state).toBe(
      "closed"
    );
  });
});

describe("resolveLearningDay", () => {
  it("leads with resumable saved work (the recoverable next action)", () => {
    const actions = [
      action({ id: "a", status: "pending", title: "Unstarted" }),
      action({ id: "b", status: "in_progress", title: "Saved" }),
    ];
    expect(resolveLearningDay(actions).next?.item.title).toBe("Saved");
  });

  it("falls back to unstarted work when nothing is saved", () => {
    const actions = [action({ id: "a", status: "pending", title: "Unstarted" })];
    expect(resolveLearningDay(actions).next?.item.title).toBe("Unstarted");
  });

  it("never presents locked work as the next action", () => {
    const actions = [
      action({
        id: "a",
        status: "pending",
        visible_from: new Date(2026, 5, 28).toISOString(),
      }),
    ];
    const day = resolveLearningDay(actions);
    expect(day.next).toBeNull();
    // It is still shown, just not as something to start.
    expect(day.rest).toHaveLength(1);
  });

  it("never presents finished work as the next action", () => {
    const actions = [
      action({ id: "a", status: "submitted" }),
      action({ id: "b", status: "completed" }),
    ];
    expect(resolveLearningDay(actions).next).toBeNull();
  });

  it("excludes the hero from the remainder", () => {
    const actions = [
      action({ id: "a", status: "in_progress" }),
      action({ id: "b", status: "pending" }),
    ];
    const day = resolveLearningDay(actions);
    expect(day.rest.map((r) => r.item.id)).toEqual(["b"]);
  });

  it("returns nothing to do when the checklist is clear", () => {
    expect(resolveLearningDay([]).next).toBeNull();
    expect(resolveLearningDay([]).rest).toEqual([]);
  });
});

describe("orderActions", () => {
  it("puts saved work first, then unstarted, then done, then blocked", () => {
    const actions = [
      action({ id: "blocked", visible_from: new Date(2026, 5, 28).toISOString() }),
      action({ id: "done", status: "completed" }),
      action({ id: "new", status: "pending" }),
      action({ id: "saved", status: "in_progress" }),
    ];
    expect(orderActions(actions).map((a) => a.item.id)).toEqual([
      "saved",
      "new",
      "done",
      "blocked",
    ]);
  });

  it("breaks ties on due date, then title", () => {
    const actions = [
      action({
        id: "later",
        status: "pending",
        due_at: new Date(2026, 5, 28).toISOString(),
      }),
      action({
        id: "sooner",
        status: "pending",
        due_at: new Date(2026, 5, 27).toISOString(),
      }),
    ];
    expect(orderActions(actions).map((a) => a.item.id)).toEqual([
      "sooner",
      "later",
    ]);
  });

  it("sorts an item with no due date after one that has a deadline", () => {
    const actions = [
      action({ id: "nodue", status: "pending", due_at: null }),
      action({
        id: "due",
        status: "pending",
        due_at: new Date(2026, 5, 30).toISOString(),
      }),
    ];
    expect(orderActions(actions).map((a) => a.item.id)).toEqual(["due", "nodue"]);
  });
});

describe("isRecoverable", () => {
  it("is true only for saved, still-open work", () => {
    expect(isRecoverable(action({ status: "in_progress" }))).toBe(true);
    expect(isRecoverable(action({ status: "pending" }))).toBe(false);
    expect(isRecoverable(action({ status: "submitted" }))).toBe(false);
    expect(
      isRecoverable(
        action({
          status: "in_progress",
          close_at: new Date(2026, 5, 20).toISOString(),
        })
      )
    ).toBe(false);
  });
});

describe("actionVerbKey", () => {
  it("chooses the verb from work and availability together", () => {
    expect(actionVerbKey(action({ status: "in_progress" }))).toBe("resume");
    expect(actionVerbKey(action({ status: "pending" }))).toBe("start");
    expect(actionVerbKey(action({ status: "submitted" }))).toBe("submitted");
    expect(actionVerbKey(action({ status: "completed" }))).toBe("viewFeedback");
  });

  it("lets availability override the work verb", () => {
    // Saved work in a not-yet-open window must not say "Resume".
    const scheduled = action({
      status: "in_progress",
      visible_from: new Date(2026, 5, 28).toISOString(),
    });
    expect(actionVerbKey(scheduled)).toBe("scheduled");
  });
});

describe("buildActions", () => {
  it("tags every item with the course it belongs to", () => {
    const actions = buildActions(COURSE, [item()], NOW, COPY);
    expect(actions[0].courseCode).toBe("LANG1512");
    expect(actions[0].courseName).toBe("Academic English");
    expect(actions[0].courseId).toBe("c1");
  });
});
