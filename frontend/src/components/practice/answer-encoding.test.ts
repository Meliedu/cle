import { describe, expect, it } from "vitest";

import {
  encodeAnswer,
  initialDraft,
  isDraftAnswered,
  matchingColumns,
  normalizeChoiceList,
  reorder,
  toQuestionType,
} from "./answer-encoding";

describe("encodeAnswer — exact backend wire shapes (B7)", () => {
  it("multiple_choice → the raw option key", () => {
    expect(encodeAnswer({ type: "multiple_choice", key: "b" })).toBe("b");
  });

  it("multiple_choice → empty string when unanswered", () => {
    expect(encodeAnswer({ type: "multiple_choice", key: null })).toBe("");
  });

  it("short_answer → the raw typed text (no JSON)", () => {
    expect(encodeAnswer({ type: "short_answer", text: "  Bonjour " })).toBe(
      "  Bonjour "
    );
  });

  it("matching → JSON-encoded {left_id: right_id} map", () => {
    const encoded = encodeAnswer({
      type: "matching",
      map: { a: "1", b: "2" },
    });
    expect(encoded).toBe(JSON.stringify({ a: "1", b: "2" }));
    expect(JSON.parse(encoded)).toEqual({ a: "1", b: "2" });
  });

  it("ordering → JSON-encoded array of ids in chosen order", () => {
    const encoded = encodeAnswer({
      type: "ordering",
      order: ["x", "y", "z"],
    });
    expect(encoded).toBe(JSON.stringify(["x", "y", "z"]));
    expect(JSON.parse(encoded)).toEqual(["x", "y", "z"]);
  });
});

describe("normalizeChoiceList — defensive builder-shape handling", () => {
  it("maps plain strings to id === label", () => {
    expect(normalizeChoiceList(["x", "y"])).toEqual([
      { id: "x", label: "x" },
      { id: "y", label: "y" },
    ]);
  });

  it("reads {id,text} objects", () => {
    expect(normalizeChoiceList([{ id: "a", text: "Apple" }])).toEqual([
      { id: "a", label: "Apple" },
    ]);
  });

  it("reads a {key: label} option map (MC)", () => {
    expect(normalizeChoiceList({ a: "Alpha", b: "Beta" })).toEqual([
      { id: "a", label: "Alpha" },
      { id: "b", label: "Beta" },
    ]);
  });
});

describe("matchingColumns", () => {
  it("splits left/right from the options payload", () => {
    const cols = matchingColumns({
      left: [{ id: "a", text: "Cat" }],
      right: [{ id: "1", text: "Chat" }],
    });
    expect(cols.left).toEqual([{ id: "a", label: "Cat" }]);
    expect(cols.right).toEqual([{ id: "1", label: "Chat" }]);
  });
});

describe("reorder — immutable up/down move", () => {
  it("moves an item down and does not mutate the input", () => {
    const input = ["x", "y", "z"];
    expect(reorder(input, 0, 1)).toEqual(["y", "x", "z"]);
    expect(input).toEqual(["x", "y", "z"]);
  });

  it("clamps at the boundaries", () => {
    expect(reorder(["x", "y"], 0, -1)).toEqual(["x", "y"]);
    expect(reorder(["x", "y"], 1, 1)).toEqual(["x", "y"]);
  });
});

describe("isDraftAnswered", () => {
  it("matching requires every left item mapped", () => {
    const columns = matchingColumns({ left: ["a", "b"], right: ["1", "2"] });
    expect(
      isDraftAnswered({ type: "matching", map: { a: "1" } }, columns)
    ).toBe(false);
    expect(
      isDraftAnswered({ type: "matching", map: { a: "1", b: "2" } }, columns)
    ).toBe(true);
  });

  it("short_answer ignores whitespace-only text", () => {
    expect(isDraftAnswered({ type: "short_answer", text: "   " })).toBe(false);
    expect(isDraftAnswered({ type: "short_answer", text: "ok" })).toBe(true);
  });
});

describe("initialDraft + toQuestionType", () => {
  it("ordering seeds the natural order from options", () => {
    expect(initialDraft("ordering", ["x", "y", "z"])).toEqual({
      type: "ordering",
      order: ["x", "y", "z"],
    });
  });

  it("coerces unknown types to multiple_choice", () => {
    expect(toQuestionType("weird")).toBe("multiple_choice");
    expect(toQuestionType("ordering")).toBe("ordering");
  });
});
