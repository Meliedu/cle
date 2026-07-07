import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../../../messages/en.json";
import { JoinFunnel } from "./join-funnel";
import {
  useEnrollByCode,
  useLookupCode,
  type CourseLookup,
} from "@/hooks/use-enrollment";
import {
  useCoursePreview,
  useReadinessSummary,
  useSubmitPhase,
  type CoursePreview,
} from "@/hooks/use-readiness";
import { usePilotConfig } from "@/hooks/use-pilot-config";
import type { PilotConfig } from "@/lib/pilot-config";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-enrollment", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-enrollment")>();
  return { ...actual, useLookupCode: vi.fn(), useEnrollByCode: vi.fn() };
});

vi.mock("@/hooks/use-readiness", () => ({
  useCoursePreview: vi.fn(),
  useReadinessSummary: vi.fn(),
  useSubmitPhase: vi.fn(),
}));

vi.mock("@/hooks/use-pilot-config", () => ({
  usePilotConfig: vi.fn(),
}));

const mockUseLookupCode = vi.mocked(useLookupCode);
const mockUseEnrollByCode = vi.mocked(useEnrollByCode);
const mockUseCoursePreview = vi.mocked(useCoursePreview);
const mockUseReadinessSummary = vi.mocked(useReadinessSummary);
const mockUseSubmitPhase = vi.mocked(useSubmitPhase);
const mockUsePilotConfig = vi.mocked(usePilotConfig);

// A pilot config whose readiness questions are entirely config-defined — the
// funnel must render THESE strings, never anything hardcoded. Two phases with
// each question kind exercised (single/multi/scale/short_text).
const MOCK_CONFIG: PilotConfig = {
  id: "cle",
  institution: "HKUST",
  course_family: "LANG",
  terminology: {},
  skill_taxonomy: [],
  confidence_scale: {
    min: -2,
    max: 2,
    labels: {
      "-2": "No idea",
      "-1": "A little",
      "0": "Some",
      "1": "Confident",
      "2": "Very confident",
    },
  },
  score_category_defaults: [],
  readiness: [
    {
      phase: "eligibility_survey",
      title: "About your background",
      intro: "Tell us where you're starting from.",
      questions: [
        {
          id: "prior_study",
          kind: "single_choice",
          prompt: "How long have you studied?",
          options: ["Never", "1-3 years"],
        },
        {
          id: "goals",
          kind: "multi_choice",
          prompt: "What are your goals?",
          options: ["Everyday conversation", "Academic writing"],
        },
      ],
    },
    {
      phase: "ready_check",
      title: "Ready check",
      intro: "Rate your confidence in each skill.",
      questions: [
        {
          id: "conf_listening",
          kind: "scale",
          prompt: "Listening confidence",
          options: [],
        },
      ],
    },
  ],
  report_cadence: { weekly: true, end_term: true },
  role_rules: {},
  locales: ["en"],
  claim_limits: {},
};

function makeLookup(overrides: Partial<CourseLookup> = {}): CourseLookup {
  return {
    course_id: "course-1",
    name: "LANG1511",
    is_open: true,
    join_mode: "code",
    code_active: true,
    ...overrides,
  };
}

function makePreview(overrides: Partial<CoursePreview> = {}): CoursePreview {
  return {
    id: "course-1",
    name: "LANG1511",
    code: "ABCD2345",
    language: "zh",
    description: "An academic Chinese course.",
    is_open: true,
    join_mode: "code",
    depth: "short",
    detail: null,
    ...overrides,
  };
}

function stubLookup(
  impl: (code: string) => Promise<CourseLookup>,
  isPending = false
) {
  const mutateAsync = vi.fn(impl);
  mockUseLookupCode.mockReturnValue({
    mutateAsync,
    isPending,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useLookupCode>);
  return mutateAsync;
}

// Shared submit spy, reset per test; captured so tests can assert the posted
// phase + answers.
let submitMutate: ReturnType<typeof vi.fn>;

function stubPreview(overrides: Partial<CoursePreview> = {}) {
  mockUseCoursePreview.mockReturnValue({
    data: makePreview(overrides),
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useCoursePreview>);
}

function renderFunnel() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <JoinFunnel />
    </NextIntlClientProvider>
  );
}

function submitCode(value: string) {
  const input = screen.getByLabelText("Course code");
  fireEvent.change(input, { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Join course" }));
}

/** Drive S003 → S005 short preview with a valid, active code. */
async function advanceToPreview() {
  stubLookup(async () => makeLookup());
  renderFunnel();
  submitCode("abcd2345");
  await screen.findByRole("button", { name: "Start readiness" });
}

/** Drive S003 → S005 → S006 eligibility survey. */
async function advanceToSurvey() {
  await advanceToPreview();
  fireEvent.click(screen.getByRole("button", { name: "Start readiness" }));
  await screen.findByText("How long have you studied?");
}

beforeEach(() => {
  vi.clearAllMocks();
  submitMutate = vi.fn(async () => ({
    phase: "eligibility_survey",
    status: "completed",
    answers: {},
    result: {},
  }));
  stubPreview();
  mockUseSubmitPhase.mockReturnValue({
    mutateAsync: submitMutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useSubmitPhase>);
  mockUsePilotConfig.mockReturnValue({
    config: MOCK_CONFIG,
    isLoaded: true,
    isError: false,
  });
  // Default enroll stub — terminal-state tests override `mutateAsync` per case.
  mockUseEnrollByCode.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useEnrollByCode>);
  mockUseReadinessSummary.mockReturnValue({
    data: {
      completed_phases: ["eligibility_survey", "ready_check"],
      recommendation: { level_hint: "intermediate", claim_limit: "" },
      answers: {},
    },
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useReadinessSummary>);
});

afterEach(() => {
  cleanup();
});

describe("JoinFunnel — S003 code entry", () => {
  it("blocks submit on a code that is not 8 characters", () => {
    const mutateAsync = stubLookup(async () => makeLookup());
    renderFunnel();

    submitCode("ABC");

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(
      screen.getByText("Enrollment codes are 8 characters.")
    ).toBeTruthy();
  });

  it("advances a valid, active code to the short preview (S005)", async () => {
    const mutateAsync = stubLookup(async () => makeLookup());
    renderFunnel();

    submitCode("abcd2345");

    // Preview eyebrow + the course name from the code-gated preview endpoint.
    await waitFor(() =>
      expect(screen.getByText("Course preview")).toBeTruthy()
    );
    expect(screen.getByText("LANG1511")).toBeTruthy();
    // Normalized to uppercase before lookup.
    expect(mutateAsync).toHaveBeenCalledWith("ABCD2345");
    expect(push).not.toHaveBeenCalled();
  });

  it("branches a deactivated code to S004 (inactive)", async () => {
    stubLookup(async () => makeLookup({ code_active: false }));
    renderFunnel();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );
    expect(screen.getByText(/no longer active/i)).toBeTruthy();
  });

  it("branches an unknown code (404) to S004 (not found)", async () => {
    stubLookup(async () => {
      throw new ApiError(404, "not found");
    });
    renderFunnel();

    submitCode("ZZZZ9999");

    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );
    expect(screen.getByText(/couldn't find a course/i)).toBeTruthy();
  });

  it("shows an inline retry message on a non-branch error, staying on S003", async () => {
    stubLookup(async () => {
      throw new ApiError(500, "boom");
    });
    renderFunnel();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't check that code. Please try again.")
      ).toBeTruthy()
    );
    // Still on the code step.
    expect(screen.getByLabelText("Course code")).toBeTruthy();
  });

  it("returns to S003 from S004 via try again", async () => {
    stubLookup(async () => makeLookup({ code_active: false }));
    renderFunnel();

    submitCode("ABCD2345");
    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByLabelText("Course code")).toBeTruthy();
  });
});

describe("JoinFunnel — S005 short preview", () => {
  it("renders the code-gated preview and starts readiness", async () => {
    await advanceToPreview();

    expect(screen.getByText("An academic Chinese course.")).toBeTruthy();
    // useCoursePreview was called with the resolved course id + code, depth short.
    expect(mockUseCoursePreview).toHaveBeenCalledWith(
      "course-1",
      "ABCD2345",
      "short"
    );
  });

  it("surfaces a not-open note when the course isn't open yet", async () => {
    stubPreview({ is_open: false });
    stubLookup(async () => makeLookup());
    renderFunnel();
    submitCode("abcd2345");

    await waitFor(() =>
      expect(screen.getByText("Not open for joining yet")).toBeTruthy()
    );
  });
});

describe("JoinFunnel — S006 eligibility survey (config-driven)", () => {
  it("renders every question from the pilot config, not hardcoded strings", async () => {
    await advanceToSurvey();

    expect(screen.getByText("About your background")).toBeTruthy();
    expect(screen.getByText("How long have you studied?")).toBeTruthy();
    expect(screen.getByText("What are your goals?")).toBeTruthy();
    // Options are config-defined too.
    expect(screen.getByRole("radio", { name: "Never" })).toBeTruthy();
    expect(
      screen.getByRole("checkbox", { name: "Everyday conversation" })
    ).toBeTruthy();
  });

  it("posts the collected answers for the phase and advances to the ready check", async () => {
    await advanceToSurvey();

    fireEvent.click(screen.getByRole("radio", { name: "Never" }));
    fireEvent.click(
      screen.getByRole("checkbox", { name: "Everyday conversation" })
    );
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(submitMutate).toHaveBeenCalledWith({
        phase: "eligibility_survey",
        answers: {
          prior_study: "Never",
          goals: ["Everyday conversation"],
        },
      })
    );
    // Advanced to S007 ready check.
    await screen.findByText("Rate your confidence in each skill.");
  });
});

/** Stub the terminal enroll mutation; returns the captured `mutateAsync` spy. */
function stubEnroll(impl: (code: string) => Promise<unknown>) {
  const mutateAsync = vi.fn(impl);
  mockUseEnrollByCode.mockReturnValue({
    mutateAsync,
    isPending: false,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useEnrollByCode>);
  return mutateAsync;
}

/**
 * Walk the funnel S003 → … → S011 summary with a valid, active `code` course so
 * the terminal tests can exercise the join CTA. Recommendation needs a computed
 * `data.result`, so we stub `useSubmitPhase` with both `mutate` (recommendation
 * POST-on-mount) and `data` here.
 */
async function advanceToSummary() {
  stubLookup(async () => makeLookup());
  mockUseSubmitPhase.mockReturnValue({
    mutate: vi.fn(),
    mutateAsync: vi.fn(async () => ({
      phase: "recommendation",
      status: "completed",
      answers: {},
      result: {},
    })),
    isPending: false,
    isError: false,
    data: {
      phase: "recommendation",
      status: "completed",
      answers: {},
      result: {
        level_hint: "intermediate",
        confidence_average: 0.5,
        claim_limit: "",
      },
    },
  } as unknown as ReturnType<typeof useSubmitPhase>);

  renderFunnel();
  submitCode("abcd2345");
  fireEvent.click(await screen.findByRole("button", { name: "Start readiness" }));
  // survey → ready check
  fireEvent.click(await screen.findByRole("button", { name: "Continue" }));
  await screen.findByText("Rate your confidence in each skill.");
  // ready check → diagnostic (no def in config → skip card)
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("No diagnostic for this course");
  // diagnostic → recommendation
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("Intermediate level");
  // recommendation → deep preview
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("What's inside");
  // deep preview → summary
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByRole("button", { name: "Join course" });
}

describe("JoinFunnel — terminal join states (S012/S013)", () => {
  it("active enrollment → S013 join success, only routes on the CTA", async () => {
    const mutateAsync = stubEnroll(async () => ({
      course: { id: "course-1", name: "LANG1511" },
      enrollment_status: "active",
    }));
    await advanceToSummary();

    fireEvent.click(screen.getByRole("button", { name: "Join course" }));

    await screen.findByText("You joined LANG1511");
    expect(mutateAsync).toHaveBeenCalledWith("ABCD2345");
    // Not auto-routed — the student chooses when to enter the workspace.
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Open course" }));
    expect(push).toHaveBeenCalledWith("/student/courses");
  });

  it("pending enrollment → awaiting-approval, NEVER routes into the workspace", async () => {
    stubEnroll(async () => ({
      course: { id: "course-1", name: "LANG1511" },
      enrollment_status: "pending",
    }));
    await advanceToSummary();

    fireEvent.click(screen.getByRole("button", { name: "Join course" }));

    await screen.findByText("Waiting for instructor approval");
    // A pending student can't read the course — no navigation whatsoever.
    expect(push).not.toHaveBeenCalled();
  });

  it("SETUP_NOT_OPEN error → S012 course-not-open", async () => {
    stubEnroll(async () => {
      throw new ApiError(409, "not open", undefined, "SETUP_NOT_OPEN");
    });
    await advanceToSummary();

    fireEvent.click(screen.getByRole("button", { name: "Join course" }));

    await screen.findByText("Course not open yet");
    expect(push).not.toHaveBeenCalled();
  });

  it("JOIN_CODE_INACTIVE error → S004 invalid/inactive", async () => {
    stubEnroll(async () => {
      throw new ApiError(409, "inactive", undefined, "JOIN_CODE_INACTIVE");
    });
    await advanceToSummary();

    fireEvent.click(screen.getByRole("button", { name: "Join course" }));

    await screen.findByText("This code is invalid or inactive");
    expect(screen.getByText(/no longer active/i)).toBeTruthy();
  });
});

describe("JoinFunnel — S007 ready check (config-driven scale)", () => {
  it("renders the confidence-scale inputs from config and can advance", async () => {
    await advanceToSurvey();
    // Move survey → ready check.
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByText("Listening confidence");

    // The −2..+2 scale labels come from config.confidence_scale.
    expect(screen.getByRole("radio", { name: "No idea" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Very confident" })).toBeTruthy();

    // Submitting the ready check posts under its own phase.
    submitMutate.mockResolvedValueOnce({
      phase: "ready_check",
      status: "completed",
      answers: {},
      result: {},
    });
    fireEvent.click(screen.getByRole("radio", { name: "Confident" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(submitMutate).toHaveBeenLastCalledWith({
        phase: "ready_check",
        answers: { conf_listening: 1 },
      })
    );
  });
});
