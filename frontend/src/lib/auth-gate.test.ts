// @vitest-environment node
//
// Server-side tests for the SSO-only host gate (the before-hook in auth.ts).
// Two layers:
//  1. Registry check — every path in EMAIL_AUTH_PATHS must exist among
//     better-auth's registered endpoints. This is what catches a renamed or
//     misremembered route (e.g. the /forget-password path that does not exist
//     in better-auth 1.6.23) before it silently un-gates production.
//  2. Behavior check — requests to each credential endpoint carrying the
//     production host are rejected with OUR 403 before any database work, so
//     these tests run without Postgres.

import { describe, expect, it } from "vitest";

import { auth, EMAIL_AUTH_PATHS } from "./auth";

const PROD_HOST = "cle-meli.hkust.edu.hk";
// Matches the default baseURL/trustedOrigins in tests (no BETTER_AUTH_URL set),
// so requests pass better-auth's origin check and reach the before-hook.
const BASE = "http://localhost:3000/api/auth";

function prodRequest(
  path: string,
  init: { method: "GET" | "POST"; body?: unknown },
): Request {
  return new Request(`${BASE}${path}`, {
    method: init.method,
    headers: {
      "content-type": "application/json",
      origin: "http://localhost:3000",
      // The hook prefers x-forwarded-host; on Vercel the edge overwrites it,
      // in tests it stands in for a request that arrived via the prod domain.
      "x-forwarded-host": PROD_HOST,
    },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

describe("EMAIL_AUTH_PATHS registry check", () => {
  it("every gated path is a real registered better-auth endpoint", () => {
    const registered = new Set(
      Object.values(auth.api)
        .map((endpoint) => (endpoint as { path?: string }).path)
        .filter((p): p is string => typeof p === "string"),
    );
    for (const path of EMAIL_AUTH_PATHS) {
      expect(registered, `"${path}" is not a registered endpoint`).toContain(
        path,
      );
    }
  });
});

describe("SSO-only production gate (server hook)", () => {
  const cases: Array<{
    name: string;
    path: string;
    method: "GET" | "POST";
    body?: unknown;
  }> = [
    {
      name: "email sign-in",
      path: "/sign-in/email",
      method: "POST",
      body: { email: "someone@ust.hk", password: "hunter2hunter2" },
    },
    {
      name: "email sign-up",
      path: "/sign-up/email",
      method: "POST",
      body: {
        name: "Someone",
        email: "someone@ust.hk",
        password: "hunter2hunter2",
      },
    },
    {
      name: "password-reset request",
      path: "/request-password-reset",
      method: "POST",
      body: { email: "someone@ust.hk", redirectTo: "/reset-password" },
    },
    {
      name: "password reset (POST)",
      path: "/reset-password",
      method: "POST",
      body: { newPassword: "hunter2hunter2", token: "some-token" },
    },
    {
      name: "password reset callback (GET)",
      path: "/reset-password/some-token",
      method: "GET",
    },
  ];

  for (const c of cases) {
    it(`rejects ${c.name} on the production host with our 403`, async () => {
      const res = await auth.handler(
        prodRequest(c.path, { method: c.method, body: c.body }),
      );
      expect(res.status).toBe(403);
      const text = await res.text();
      // Our hook's message — distinguishes the gate from other 403s
      // (e.g. better-auth's origin check).
      expect(text).toContain("HKUST");
    });
  }

  it("does not over-block non-credential endpoints (/ok) on the production host", async () => {
    const res = await auth.handler(prodRequest("/ok", { method: "GET" }));
    expect(res.status).toBe(200);
  });

  it("blocks a spoofed X-Forwarded-Host=dev when the real Host is production", async () => {
    // Fail-closed proof: an attacker on the prod domain who spoofs the
    // forwarded header to a dev host must NOT re-enable the credential path —
    // the authoritative Host still says prod, so `.every()` rejects it.
    const req = new Request(`${BASE}/sign-in/email`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        origin: "http://localhost:3000",
        host: PROD_HOST,
        "x-forwarded-host": "cle-meli-dev.hkust.edu.hk",
      },
      body: JSON.stringify({ email: "a@ust.hk", password: "hunter2hunter2" }),
    });
    const res = await auth.handler(req);
    expect(res.status).toBe(403);
    expect(await res.text()).toContain("HKUST");
  });
});
