import { describe, expect, it } from "vitest";

import { DEFAULT_REDIRECT, sanitizeRedirect } from "@/lib/redirect";

describe("sanitizeRedirect", () => {
  const cases: ReadonlyArray<{
    name: string;
    input: string | null;
    expected: string;
  }> = [
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
      name: "rejects protocol-relative URLs",
      input: "//evil.com",
      expected: DEFAULT_REDIRECT,
    },
    {
      name: "rejects backslash protocol-relative escape (WHATWG normalizes \\ to /)",
      input: "/\\evil.com",
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
