import { describe, expect, it } from "vitest";

import { DEFAULT_REDIRECT, sanitizeRedirect } from "@/lib/redirect";

describe("sanitizeRedirect", () => {
  const cases: ReadonlyArray<{
    name: string;
    input: string | null;
    expected: string;
  }> = [
    // --- allowed: same-origin path-absolute targets -----------------------
    {
      name: "allows a plain internal path",
      input: "/dashboard",
      expected: "/dashboard",
    },
    {
      name: "allows a nested internal path",
      input: "/teacher/dashboard",
      expected: "/teacher/dashboard",
    },
    {
      name: "allows internal paths with query strings",
      input: "/dashboard/courses?tab=materials",
      expected: "/dashboard/courses?tab=materials",
    },
    {
      name: "normalizes an interior backslash to a slash (same-origin, safe)",
      input: "/a\\b",
      expected: "/a/b",
    },
    // --- rejected: cross-origin escapes ------------------------------------
    {
      name: "rejects protocol-relative URLs",
      input: "//evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects backslash protocol-relative escape (parser folds \\ to /, origin becomes evil.com)",
      input: "/\\evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects TAB-obfuscated protocol-relative (parser strips \\t before parsing)",
      input: "/\t/evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects LF-obfuscated protocol-relative (parser strips \\n before parsing)",
      input: "/\n/evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects CR-obfuscated protocol-relative (parser strips \\r before parsing)",
      input: "/\r/evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects TAB + backslash combo (strips \\t, folds \\ — origin becomes evil.com)",
      input: "/\t\\evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects paths that normalize to a protocol-relative pathname",
      input: "/.//evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects absolute URLs",
      input: "https://evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects scheme URLs (XSS vector)",
      input: "javascript:alert(1)",
      expected: DEFAULT_REDIRECT,
    },
    // --- rejected: nothing usable ------------------------------------------
    {
      name: "falls back on null",
      input: null,
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "falls back on empty string",
      input: "",
      expected: DEFAULT_REDIRECT,
    },
  ];

  it.each(cases)("$name", ({ input, expected }) => {
    expect(sanitizeRedirect(input)).toBe(expected);
  });
});
