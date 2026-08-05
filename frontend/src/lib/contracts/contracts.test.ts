import { describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/lib/api";
import {
  canTransitionSession,
  courseActionVerb,
  courseLifecycle,
  rollUpSources,
  sessionActionVerb,
  setupIsAvailable,
  sourceIsRetryable,
  studentWorkVerb,
  learnerCanWork,
  SESSION_READINESS_VALUES,
  type SessionReadiness,
} from "./state";
import {
  isUserSafeText,
  safeErrorFromCode,
  toSafeError,
} from "./safe-error";

describe("courseLifecycle", () => {
  it("reads published only when setup and context both agree", () => {
    expect(
      courseLifecycle({ setup_status: "published", context_status: "approved" })
    ).toBe("published");
    // Published setup with an unapproved context is NOT published. This is
    // the pre-existing isCoursePublished rule, preserved.
    expect(
      courseLifecycle({ setup_status: "published", context_status: "pending" })
    ).toBe("draft");
  });

  it("distinguishes an untouched draft from a started setup", () => {
    expect(courseLifecycle({ setup_checklist: {} })).toBe("draft");
    expect(courseLifecycle({ setup_checklist: { basics: false } })).toBe("draft");
    expect(courseLifecycle({ setup_checklist: { basics: true } })).toBe("setup");
    expect(courseLifecycle({ setup_status: "in_progress" })).toBe("setup");
  });

  it("treats archive as terminal regardless of setup state", () => {
    expect(
      courseLifecycle({
        setup_status: "published",
        context_status: "approved",
        archived_at: "2026-01-01T00:00:00Z",
      })
    ).toBe("archived");
  });
});

describe("setup is transient", () => {
  it("exposes Setup only while the course is incomplete", () => {
    expect(setupIsAvailable("draft")).toBe(true);
    expect(setupIsAvailable("setup")).toBe(true);
    // Handoff removal rule 02: no persistent Setup item after publication.
    expect(setupIsAvailable("published")).toBe(false);
    expect(setupIsAvailable("archived")).toBe(false);
  });
});

describe("courseActionVerb", () => {
  it("changes the verb with status (Plate 02, rule 2)", () => {
    expect(courseActionVerb("published")).toBe("open");
    expect(courseActionVerb("setup")).toBe("continueSetup");
    expect(courseActionVerb("draft")).toBe("continueSetup");
    expect(courseActionVerb("archived")).toBe("view");
  });
});

describe("source readiness", () => {
  it("offers retry only for recoverable failures", () => {
    expect(sourceIsRetryable("recoverable_error")).toBe(true);
    expect(sourceIsRetryable("blocking_error")).toBe(false);
    expect(sourceIsRetryable("processing")).toBe(false);
  });

  it("rolls a source set up into publish readiness", () => {
    const rollup = rollUpSources([
      "ready",
      "ready",
      "processing",
      "recoverable_error",
    ]);
    expect(rollup).toEqual({
      total: 4,
      ready: 2,
      inFlight: 1,
      needsAttention: 1,
      blocking: 0,
    });
  });

  it("counts a blocking error separately from a recoverable one", () => {
    expect(rollUpSources(["blocking_error"]).blocking).toBe(1);
    expect(rollUpSources(["recoverable_error"]).blocking).toBe(0);
  });
});

describe("session state machine", () => {
  it("maps each readiness to exactly one verb", () => {
    const verbs = SESSION_READINESS_VALUES.map((value) =>
      sessionActionVerb(value)
    );
    expect(verbs).toEqual(["prepare", "review", "open", "monitor", "close"]);
  });

  it("guards illegal transitions", () => {
    expect(canTransitionSession("ready", "live")).toBe(true);
    expect(canTransitionSession("live", "closed")).toBe(true);
    // A closed session is terminal; a draft cannot jump straight to live.
    expect(canTransitionSession("closed", "live")).toBe(false);
    expect(canTransitionSession("draft", "live")).toBe(false);
  });

  it("never allows a transition out of closed", () => {
    for (const target of SESSION_READINESS_VALUES) {
      expect(canTransitionSession("closed", target as SessionReadiness)).toBe(
        false
      );
    }
  });
});

describe("visibility is orthogonal to lifecycle", () => {
  it("does not open learner access just because a course is published", () => {
    // Publishing sets lifecycle; it does not set visibility. A hidden or
    // scheduled course stays closed to learners.
    expect(learnerCanWork("hidden")).toBe(false);
    expect(learnerCanWork("scheduled")).toBe(false);
    expect(learnerCanWork("open")).toBe(true);
    expect(learnerCanWork("closed")).toBe(false);
  });
});

describe("studentWorkVerb", () => {
  it("maps saved progress to Resume", () => {
    expect(studentWorkVerb("not_started")).toBe("start");
    expect(studentWorkVerb("in_progress")).toBe("resume");
    expect(studentWorkVerb("submitted")).toBe("submitted");
    expect(studentWorkVerb("reviewed")).toBe("viewFeedback");
  });
});

describe("isUserSafeText", () => {
  it("rejects the exact string the live product leaked (Plate 05, note 3)", () => {
    expect(
      isUserSafeText(
        "AttributeError: 'Settings' object has no attribute 'llm_primary_model'"
      )
    ).toBe(false);
  });

  it("rejects stack traces, module paths, and object keys", () => {
    expect(isUserSafeText("Traceback (most recent call last)")).toBe(false);
    expect(isUserSafeText('File "app/services/parser.py", line 88')).toBe(false);
    expect(isUserSafeText("app.services.pipeline failed")).toBe(false);
    expect(isUserSafeText("boto3 ClientError on r2 bucket")).toBe(false);
    expect(
      isUserSafeText("postgresql+asyncpg://user:pw@db:5432/langassistant")
    ).toBe(false);
    expect(
      isUserSafeText("course 3f2504e0-4f89-11d3-9a0c-0305e82c3301 missing")
    ).toBe(false);
    expect(isUserSafeText("HTTP 500 from upstream")).toBe(false);
  });

  it("accepts genuine user copy", () => {
    expect(isUserSafeText("This course still needs a schedule.")).toBe(true);
    expect(isUserSafeText("Add at least one source before publishing.")).toBe(
      true
    );
  });

  it("rejects empty and oversized strings", () => {
    expect(isUserSafeText("   ")).toBe(false);
    expect(isUserSafeText("x".repeat(241))).toBe(false);
  });
});

describe("the fetch boundary is the backstop", () => {
  it("drops an unsafe backend message before it becomes ApiError.message", () => {
    // ~30 components render `error.message` directly. Sanitising at
    // construction is what stops a future `raise HTTPException(400,
    // detail=str(exc))` from putting an exception on screen through all of
    // them at once.
    const raw =
      "AttributeError: 'Settings' object has no attribute 'llm_primary_model'";
    const error = new ApiError(400, userFacingMessageFor(400, raw), raw);
    expect(error.message).not.toContain("AttributeError");
    expect(error.detail).toBeUndefined();
  });

  it("keeps a safe backend message on detail only when it is typed", () => {
    const safe = "Add a schedule before publishing.";

    // Typed: the backend asserted this is deliberate user copy.
    const typed = new ApiError(422, safe, safe, "SETUP_INCOMPLETE");
    expect(typed.message).toBe(safe);
    expect(typed.detail).toBe(safe);

    // Untyped: indistinguishable from an exception that escaped a handler, so
    // it is dropped even though it happens to read as friendly copy. The
    // predicate alone fails open, which is why the code is what gates this.
    const untyped = new ApiError(422, safe, safe);
    expect(untyped.detail).toBeUndefined();
  });
});

/**
 * `userFacingMessage` is module-private in `lib/api.ts`; this mirrors what
 * `apiFetch` passes so the assertion above exercises the real constructor
 * behaviour rather than a hand-built string.
 */
function userFacingMessageFor(status: number, message: string): string {
  return isUserSafeText(message)
    ? message
    : `Request failed (HTTP ${status}).`;
}

describe("toSafeError", () => {
  it("never surfaces an unsafe backend detail", () => {
    const raw =
      "AttributeError: 'Settings' object has no attribute 'llm_primary_model'";
    const error = new ApiError(500, "Something went wrong", raw);
    const safe = toSafeError(error, { objectName: "Week 1 reading.pdf" });

    expect(safe.title).not.toContain("AttributeError");
    expect(safe.title).not.toContain("llm_primary_model");
    expect(safe.title).toContain("Week 1 reading.pdf");
    expect(safe.preserved).toMatch(/saved/i);
    expect(safe.nextAction.length).toBeGreaterThan(0);
  });

  it("keeps a typed backend message when it is genuinely user copy", () => {
    const error = new ApiError(
      422,
      "Add a schedule first.",
      "Add a schedule first.",
      "unknown"
    );
    expect(toSafeError(error).title).toBe("Add a schedule first.");
  });

  it("prefers the typed code over the HTTP status", () => {
    const error = new ApiError(500, "…", undefined, "unreadable_file");
    const safe = toSafeError(error, { objectName: "syllabus.pdf" });
    expect(safe.code).toBe("unreadable_file");
    expect(safe.retryable).toBe(true);
    expect(safe.severity).toBe("recoverable");
  });

  it("falls back to the status when no typed code is present", () => {
    expect(toSafeError(new ApiError(403, "…")).code).toBe("permission_denied");
    expect(toSafeError(new ApiError(404, "…")).code).toBe("not_found");
    expect(toSafeError(new ApiError(429, "…")).code).toBe("rate_limited");
  });

  it("classifies a fetch failure as a network error", () => {
    expect(toSafeError(new TypeError("Failed to fetch")).code).toBe("network");
  });

  it("never offers Retry for a failure only an operator can fix", () => {
    // Mirrors the backend RETRYABLE_CODES, which excludes ANALYSIS_UNAVAILABLE:
    // it is the bucket for our own defects and misconfiguration (the 4 Aug 2026
    // revoked OpenRouter key landed here), where a retry re-runs download,
    // parse and embedding to fail identically and bills us for it.
    const safe = safeErrorFromCode("analysis_unavailable", {
      objectName: "syllabus.pdf",
    });
    expect(safe.retryable).toBe(false);
    // Still recoverable: the route, the files and the finished steps survive.
    expect(safe.severity).toBe("recoverable");
    expect(safe.nextAction).not.toMatch(/retry/i);
  });

  it("tells the user to re-upload a file that is no longer stored", () => {
    // The two uploads destroyed by the delete-on-failure bug carried
    // `storage_unavailable`, whose "Retry in a moment" can never succeed
    // against bytes that no longer exist.
    const safe = safeErrorFromCode("file_missing", { objectName: "syllabus.pdf" });
    expect(safe.retryable).toBe(false);
    expect(safe.severity).toBe("blocking");
    expect(safe.nextAction).toMatch(/upload/i);
    expect(safe.title).toContain("syllabus.pdf");
  });

  it("still offers Retry when the provider is merely busy", () => {
    // The counterpart to the test above. Both come from the same LLM step, so
    // if they shared a code the Retry button would have to be wrong for one of
    // them: a revoked key never recovers, a 429 usually does.
    const safe = safeErrorFromCode("provider_unavailable", {
      objectName: "syllabus.pdf",
    });
    expect(safe.retryable).toBe(true);
    expect(safe.severity).toBe("recoverable");
    expect(safe.title).toContain("syllabus.pdf");
  });

  it("marks unsupported formats as blocking, not retryable", () => {
    const safe = safeErrorFromCode("unsupported_format", {
      objectName: "notes.key",
    });
    expect(safe.retryable).toBe(false);
    expect(safe.severity).toBe("blocking");
    expect(safe.title).toContain("notes.key");
  });

  it("always produces all four required clauses", () => {
    const codes = [
      "unreadable_file",
      "unsupported_format",
      "file_too_large",
      "empty_document",
      "storage_unavailable",
      "file_missing",
      "analysis_unavailable",
      "provider_unavailable",
      "timeout",
      "permission_denied",
      "not_found",
      "rate_limited",
      "network",
      "unknown",
    ] as const;
    for (const code of codes) {
      const safe = safeErrorFromCode(code, { objectName: "thing.pdf" });
      expect(safe.title.length).toBeGreaterThan(0);
      expect(safe.consequence.length).toBeGreaterThan(0);
      expect(safe.preserved.length).toBeGreaterThan(0);
      expect(safe.nextAction.length).toBeGreaterThan(0);
      expect(isUserSafeText(safe.title)).toBe(true);
      expect(isUserSafeText(safe.consequence)).toBe(true);
    }
  });
});


// ---------------------------------------------------------------------------
// Regression: the safe-text predicate is a DENYLIST and therefore fails open.
// These strings are all realistic backend output that no pattern catches. They
// must not reach users, so the boundary in lib/api.ts gates on a typed `code`
// rather than trusting the predicate alone. Found by code review of 63bd2d3.
// ---------------------------------------------------------------------------

const UNTYPED_BACKEND_STRINGS = [
  "KeyError 'course_id'",
  'duplicate key value violates unique constraint "ix_courses_code"',
  "column courses.setup_status does not exist",
  'relation "documents" does not exist',
  "invalid literal for int() with base 10: 'abc'",
  "Expecting value: line 1 column 1 (char 0)",
  "Connection refused to 127.0.0.1:5432",
  "cannot import name 'Settings' from config",
  "psycopg.errors.UniqueViolation",
  "Field required [type=missing, input_value={'name': 'x'}]",
  "Generation failed after 3 retries",
  "model did not return valid JSON",
];

describe("untyped backend messages never reach users", () => {
  it.each(UNTYPED_BACKEND_STRINGS)(
    "a 400 carrying %j but no code renders generic copy",
    async (leaked) => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: { message: leaked } }),
      });
      vi.stubGlobal("fetch", fetchMock);

      await expect(apiFetch("/anything")).rejects.toSatisfy((err: unknown) => {
        const e = err as ApiError;
        expect(e.message).not.toContain(leaked);
        expect(e.message).toBe("Request failed (HTTP 400).");
        return true;
      });

      vi.unstubAllGlobals();
    }
  );

  it("still surfaces a message the backend typed with a code", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        error: { code: "SETUP_INCOMPLETE", message: "Finish the schedule step first." },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/anything")).rejects.toThrow(
      "Finish the schedule step first."
    );

    vi.unstubAllGlobals();
  });

  it("keeps a leaked string out of .detail as well as .message", () => {
    // .detail is rendered directly by several components to get a more
    // specific message than the status fallback, so it needs the same guard.
    const err = new ApiError(400, "Request failed.", "psycopg.errors.UniqueViolation");
    expect(err.detail).toBeUndefined();
  });
});
