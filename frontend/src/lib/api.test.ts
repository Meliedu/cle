import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api";

function mockResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiFetch error parsing", () => {
  it("lifts a typed code from FastAPI's raw { detail: { code, message } }", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(409, {
        detail: { code: "SETUP_INCOMPLETE", message: "Finish setup first." },
      })
    );

    await expect(apiFetch("/courses/c1/setup/publish")).rejects.toMatchObject({
      status: 409,
      code: "SETUP_INCOMPLETE",
    });
  });

  it("lifts a typed code from the app envelope { error: { code, message } }", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(409, {
        error: { code: "SETUP_NOT_OPEN", message: "Not open." },
      })
    );

    try {
      await apiFetch("/anything");
      throw new Error("expected apiFetch to reject");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).code).toBe("SETUP_NOT_OPEN");
    }
  });

  it("leaves code undefined for a bare string detail", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      mockResponse(404, { detail: "Course not found" })
    );

    await expect(apiFetch("/missing")).rejects.toMatchObject({
      status: 404,
      code: undefined,
    });
  });
});
