import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import zhMessages from "../../../messages/zh-Hant.json";
import {
  REVIEW_FLAG_CODES,
  REVIEW_FLAG_SEVERITY,
  flagSeverity,
  hasBlockingFlag,
  isKnownFlag,
  sortFlags,
} from "./review-flags";

describe("review flag severity", () => {
  it("classifies a disputed key as blocking, not merely reviewable", () => {
    // An item with no agreed answer cannot be approved away by a reviewer;
    // the content has to be fixed first.
    expect(flagSeverity("item_key_disputed")).toBe("blocking");
    expect(flagSeverity("form_compromised")).toBe("blocking");
  });

  it("treats the test ceiling as advisory rather than a problem", () => {
    expect(flagSeverity("high_band_ceiling")).toBe("advisory");
  });

  it("treats an unrecognised code as needing review rather than ignoring it", () => {
    // A trigger a future backend adds is still a trigger. Defaulting to
    // "advisory" would quietly downgrade something nobody has assessed.
    expect(isKnownFlag("some_future_trigger")).toBe(false);
    expect(flagSeverity("some_future_trigger")).toBe("review");
  });

  it("assigns a severity to every code the scorer can emit", () => {
    for (const code of REVIEW_FLAG_CODES) {
      expect(REVIEW_FLAG_SEVERITY[code]).toBeDefined();
    }
  });
});

describe("flag ordering", () => {
  it("puts blocking flags first so the reviewer sees the stopper", () => {
    const sorted = sortFlags([
      "high_band_ceiling",
      "incomplete_answers",
      "item_key_disputed",
    ]);
    expect(sorted[0]).toBe("item_key_disputed");
    expect(sorted[sorted.length - 1]).toBe("high_band_ceiling");
  });

  it("is stable for equal severities", () => {
    expect(sortFlags(["lower_band_break", "attempt_spread"])).toEqual([
      "attempt_spread",
      "lower_band_break",
    ]);
  });

  it("does not mutate its input", () => {
    const input = ["high_band_ceiling", "item_key_disputed"];
    sortFlags(input);
    expect(input).toEqual(["high_band_ceiling", "item_key_disputed"]);
  });
});

describe("blocking detection", () => {
  it("is false when only reviewable and advisory flags are present", () => {
    expect(hasBlockingFlag(["incomplete_answers", "high_band_ceiling"])).toBe(false);
  });

  it("is true when any flag is blocking", () => {
    expect(hasBlockingFlag(["incomplete_answers", "item_key_disputed"])).toBe(true);
  });

  it("is false for an empty list", () => {
    expect(hasBlockingFlag([])).toBe(false);
  });
});

describe("flag copy", () => {
  const flagsEn = messages.teacher.placement.flag as Record<string, string>;
  const flagsZh = zhMessages.teacher.placement.flag as Record<string, string>;

  it("has a label and an explanation for every code", () => {
    // A code that reaches the UI without copy renders as a raw token, which is
    // exactly the kind of leak the safe-text rules exist to prevent.
    for (const code of REVIEW_FLAG_CODES) {
      expect(flagsEn[code], `missing label for ${code}`).toBeTruthy();
      expect(flagsEn[`${code}Detail`], `missing detail for ${code}`).toBeTruthy();
    }
  });

  it("is translated for every code", () => {
    for (const code of REVIEW_FLAG_CODES) {
      expect(flagsZh[code], `missing zh label for ${code}`).toBeTruthy();
      expect(flagsZh[`${code}Detail`], `missing zh detail for ${code}`).toBeTruthy();
    }
  });

  it("never presents a pattern flag as an accusation", () => {
    // The scorer flags straight-lining heuristically. Copy that reads as
    // "cheating" would put an unevidenced allegation in front of a reviewer.
    const detail = flagsEn.response_pattern_anomalyDetail.toLowerCase();
    for (const word of ["cheat", "cheating", "dishonest", "fraud"]) {
      expect(detail).not.toContain(word);
    }
  });
});

describe("mirror of the backend trigger list", () => {
  it("knows every flag the scorer can emit", () => {
    // REVIEW_FLAG_CODES is hand-maintained, and the header used to claim an
    // exhaustiveness check that did not exist. This is that check: it reads the
    // real Python source, so a trigger added on the backend fails here instead
    // of reaching next-intl as a missing key in front of a reviewer.
    const source = readFileSync(
      resolve(__dirname, "../../../../backend/app/services/placement_scoring.py"),
      "utf8"
    );
    const emitted = new Set(
      [...source.matchAll(/flags\.append\(\s*"([a-z_]+)"\s*\)/g)].map((m) => m[1])
    );
    expect(emitted.size).toBeGreaterThan(5);

    const known = new Set<string>(REVIEW_FLAG_CODES);
    const missing = [...emitted].filter((code) => !known.has(code));
    expect(missing, `backend emits flags the UI cannot render: ${missing}`).toEqual([]);
  });

  it("does not carry codes the backend no longer emits", () => {
    const source = readFileSync(
      resolve(__dirname, "../../../../backend/app/services/placement_scoring.py"),
      "utf8"
    );
    const emitted = new Set(
      [...source.matchAll(/flags\.append\(\s*"([a-z_]+)"\s*\)/g)].map((m) => m[1])
    );
    const stale = REVIEW_FLAG_CODES.filter((code) => !emitted.has(code));
    expect(stale, `UI carries dead flag codes: ${stale}`).toEqual([]);
  });
});
