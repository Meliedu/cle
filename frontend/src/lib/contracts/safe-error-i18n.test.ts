import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import zhHant from "../../../messages/zh-Hant.json";
import { SAFE_ERROR_CODES } from "./safe-error";

/**
 * Locale parity for the safe-error contract.
 *
 * `SAFE_COPY`'s `Record<SafeErrorCode, …>` type already forces English copy for
 * every code, but nothing forced a *translation*. `useSafeError` calls
 * next-intl's `t()` inside a try/catch meant to fall back to the English
 * contract, except next-intl does not throw on a missing key: it returns the
 * dotted key path. So a code with no message entry renders literal
 * `safeError.file_missing.titleNamed` into the instructor's recovery banner,
 * and the catch never runs. That is exactly what happened to `file_missing` and
 * `provider_unavailable`.
 */

const LOCALES = { en, "zh-Hant": zhHant } as const;
const FIELDS = [
  "titleNamed",
  "title",
  "consequence",
  "preserved",
  "nextAction",
] as const;

describe("safe-error locale parity", () => {
  for (const [locale, messages] of Object.entries(LOCALES)) {
    const safeError = (messages as Record<string, unknown>).safeError as
      | Record<string, Record<string, string>>
      | undefined;

    it(`${locale} defines every safe-error code`, () => {
      expect(safeError, `${locale}.json has no safeError section`).toBeDefined();
      const missing = SAFE_ERROR_CODES.filter((code) => !safeError?.[code]);
      expect(missing, `untranslated codes in ${locale}`).toEqual([]);
    });

    it(`${locale} defines every field for every code`, () => {
      const gaps: string[] = [];
      for (const code of SAFE_ERROR_CODES) {
        const entry = safeError?.[code];
        if (!entry) continue;
        for (const field of FIELDS) {
          const value = entry[field];
          if (typeof value !== "string" || value.trim() === "") {
            gaps.push(`${code}.${field}`);
          }
        }
      }
      expect(gaps, `missing/empty fields in ${locale}`).toEqual([]);
    });

    // Deliberately NOT asserted: that every `titleNamed` interpolates
    // `{object}`. Codes whose contract title ignores its argument
    // (permission_denied, rate_limited, network, all `title: () => ...`) are
    // correctly object-free in the locale files too.
  }
});
