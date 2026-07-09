import { describe, expect, it } from "vitest";

import { isEmailPasswordHost } from "./auth-flags";

describe("isEmailPasswordHost", () => {
  it("allows the dev domain and localhost (with or without a port)", () => {
    expect(isEmailPasswordHost("cle-meli-dev.hkust.edu.hk")).toBe(true);
    expect(isEmailPasswordHost("localhost")).toBe(true);
    expect(isEmailPasswordHost("localhost:3000")).toBe(true);
    expect(isEmailPasswordHost("127.0.0.1")).toBe(true);
    expect(isEmailPasswordHost("127.0.0.1:3000")).toBe(true);
  });

  it("rejects the production host — SSO-only", () => {
    expect(isEmailPasswordHost("cle-meli.hkust.edu.hk")).toBe(false);
  });

  it("is case-insensitive on the hostname", () => {
    expect(isEmailPasswordHost("CLE-MELI-DEV.HKUST.EDU.HK")).toBe(true);
    expect(isEmailPasswordHost("CLE-MELI.HKUST.EDU.HK")).toBe(false);
  });

  it("fails closed on unknown, empty, or missing hosts", () => {
    expect(isEmailPasswordHost("some-preview.vercel.app")).toBe(false);
    expect(isEmailPasswordHost("evil.example.com")).toBe(false);
    expect(isEmailPasswordHost("")).toBe(false);
    expect(isEmailPasswordHost(null)).toBe(false);
    expect(isEmailPasswordHost(undefined)).toBe(false);
  });
});
