import { describe, expect, it } from "vitest";

import { courseTitle, displayLanguage } from "./format";

describe("courseTitle", () => {
  it("drops a code prefix the name already repeats", () => {
    expect(courseTitle("LANG1511", "LANG1511 · Chinese I")).toBe("Chinese I");
    expect(courseTitle("LANG1511", "LANG1511 - Chinese I")).toBe("Chinese I");
    expect(courseTitle("LANG1511", "LANG1511: Chinese I")).toBe("Chinese I");
  });

  it("leaves a name that does not repeat the code alone", () => {
    expect(courseTitle("LANG1511", "Chinese I")).toBe("Chinese I");
  });

  it("never returns empty when the name is only the code", () => {
    // Blanking the line would be worse than repeating it.
    expect(courseTitle("LANG1511", "LANG1511")).toBe("LANG1511");
  });

  it("is case-insensitive about the prefix", () => {
    expect(courseTitle("lang1511", "LANG1511 · Chinese I")).toBe("Chinese I");
  });

  it("passes the name through when there is no code", () => {
    expect(courseTitle(null, "Chinese I")).toBe("Chinese I");
  });

  it("never bites into a longer token that merely starts with the code", () => {
    // A shorter code that is a strict string-prefix of the name's first token
    // must not slice mid-token and return a mangled fragment.
    expect(courseTitle("LANG151", "LANG1511 · Chinese I")).toBe(
      "LANG1511 · Chinese I"
    );
    expect(courseTitle("LANG1511", "LANG15110 · Extra number")).toBe(
      "LANG15110 · Extra number"
    );
  });
});

describe("displayLanguage", () => {
  it("title-cases raw metadata casing", () => {
    expect(displayLanguage("chinese")).toBe("Chinese");
    expect(displayLanguage("ACADEMIC ENGLISH")).toBe("Academic English");
  });

  it("leaves already-clean values unchanged", () => {
    expect(displayLanguage("Chinese")).toBe("Chinese");
  });
});
