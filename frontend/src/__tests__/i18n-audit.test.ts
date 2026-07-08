import { describe, expect, it } from "vitest";

// The audit script is the single source of truth for the scan (dirs, idiom
// extraction, en.json resolution). This guard runs it and turns the
// MISSING-KEY result into a hard failure: every next-intl key referenced in the
// P4–P7 route trees + components must resolve to a real key in en.json.
//
// The hardcoded-string heuristic is intentionally a SOFT report (console
// warning) — it stays a warning, never a hard fail, so the guard cannot flake
// on a false-positive literal.
import { runAudit } from "../../scripts/i18n-audit.mjs";

describe("i18n key audit (P4–P7 UI)", () => {
  const result = runAudit();

  it("scanned the P4–P7 surface and found key references", () => {
    // Sanity: the extractor is actually seeing the real code, not an empty set.
    expect(result.scannedFiles).toBeGreaterThan(0);
    expect(result.referenceCount).toBeGreaterThan(0);
  });

  it("every referenced next-intl key resolves in messages/en.json", () => {
    if (result.missing.length > 0) {
      const detail = result.missing
        .map(
          (m) =>
            `  ${m.file}:${m.line}  ${m.kind} "${m.key}" (tried: ${m.resolvedAs.join(", ")})`
        )
        .join("\n");
      throw new Error(
        `${result.missing.length} referenced i18n key(s) missing from en.json:\n${detail}`
      );
    }
    expect(result.missing).toEqual([]);
  });

  it("reports suspected hardcoded strings as warnings (soft, non-failing)", () => {
    if (result.warnings.length > 0) {
      // eslint-disable-next-line no-console
      console.warn(
        `[i18n-audit] ${result.warnings.length} suspected hardcoded string(s) — review (soft):\n` +
          result.warnings
            .map((w) => `  [${w.kind}] ${w.file}:${w.line}  "${w.text}"`)
            .join("\n")
      );
    }
    // Soft by design: assert the report is an array, never its length.
    expect(Array.isArray(result.warnings)).toBe(true);
  });
});
