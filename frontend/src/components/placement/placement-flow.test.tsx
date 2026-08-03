import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { PlacementFlow } from "./placement-flow";
import {
  useMyPlacementAttempts,
  usePlacementAttempt,
  usePlacementIntro,
  usePlacementResult,
  useStartPlacementAttempt,
  useAdvancePlacementAttempt,
} from "@/hooks/use-placement";

vi.mock("@/hooks/use-placement", async () => {
  const actual = await vi.importActual<Record<string, unknown>>(
    "@/hooks/use-placement"
  );
  return {
    ...actual,
    usePlacementIntro: vi.fn(),
    usePlacementAttempt: vi.fn(),
    usePlacementResult: vi.fn(),
    useMyPlacementAttempts: vi.fn(),
    useStartPlacementAttempt: vi.fn(),
    useAdvancePlacementAttempt: vi.fn(),
  };
});

// The sitting is exercised by the browser walkthrough; stub it so these tests
// stay about which screen a given backend state produces.
vi.mock("@/components/placement/placement-sitting", () => ({
  PlacementSitting: () => <div>SITTING</div>,
}));

const mockIntro = vi.mocked(usePlacementIntro);
const mockAttempt = vi.mocked(usePlacementAttempt);
const mockResult = vi.mocked(usePlacementResult);
const mockAttempts = vi.mocked(useMyPlacementAttempts);
const mockStart = vi.mocked(useStartPlacementAttempt);
const mockAdvance = vi.mocked(useAdvancePlacementAttempt);

afterEach(cleanup);

const INTRO = {
  available: true,
  unavailable_reason: null,
  version_code: "v1.3",
  duration_minutes: 30,
  section_counts: { listening: 12, language_use: 6, reading: 12 },
  total_items: 30,
  max_attempts: 3,
  attempts_used: 1,
  attempts_remaining: 2,
  purpose: "This is an internal Meli/CLE placement screener.",
  privacy: "Results support a course recommendation and CLE review.",
  window_opens_at: null,
  window_closes_at: null,
  comparability_note: "Not statistically equated.",
};

function setup(state: string, released = false) {
  mockIntro.mockReturnValue({ data: INTRO, isLoading: false, isError: false } as never);
  mockAttempts.mockReturnValue({
    data: [{ id: "a1", state }],
    isLoading: false,
  } as never);
  mockAttempt.mockReturnValue({
    data: { id: "a1", state, attempt_number: 1, form_code: "A", items: [], saved_responses: {} },
    isLoading: false,
  } as never);
  mockResult.mockReturnValue({
    data: {
      attempt_id: "a1",
      state,
      released,
      submitted_at: null,
      recommended_course: released ? "LANG1513" : null,
      claim_limit: "Not an official HSK result.",
    },
    isLoading: false,
  } as never);
  mockStart.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
  mockAdvance.mockReturnValue({ mutate: vi.fn(), isPending: false } as never);

  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <PlacementFlow />
    </NextIntlClientProvider>
  );
}

describe("screen for each backend state", () => {
  it("shows the pending-review screen after submission", () => {
    setup("review_pending");
    expect(screen.getByText(/your answers are with cle/i)).toBeTruthy();
  });

  it("shows the recommendation once released", () => {
    setup("released", true);
    expect(screen.getByText("LANG1513")).toBeTruthy();
  });

  it("does not claim answers are under review when the timer expired empty", () => {
    // The expiry sweep only uses `expired` when nothing was answered. Telling
    // that learner their answers are with CLE would be a plain lie.
    setup("expired");
    expect(screen.queryByText(/your answers are with cle/i)).toBeNull();
    expect(screen.getByText(/time ran out before you answered anything/i)).toBeTruthy();
  });

  it("tells an abandoned attempt it cost them nothing", () => {
    setup("abandoned");
    expect(screen.queryByText(/your answers are with cle/i)).toBeNull();
    expect(screen.getByText(/did not use up one of your attempts/i)).toBeTruthy();
  });

  it("explains a technical review rather than calling it a result", () => {
    setup("technical_review");
    expect(screen.queryByText(/your answers are with cle/i)).toBeNull();
    expect(screen.getByText(/checking a technical problem/i)).toBeTruthy();
  });

  it("offers a retry after an expiry but not during a technical review", () => {
    setup("expired");
    expect(screen.getByRole("button", { name: /start the screener again/i })).toBeTruthy();
    cleanup();

    // Nothing for the learner to redo while CLE is still working out what
    // happened; a retry here would burn an attempt on our problem.
    setup("technical_review");
    expect(screen.queryByRole("button", { name: /start the screener again/i })).toBeNull();
  });

  it("shows the invalidated state as its own thing", () => {
    setup("invalidated");
    expect(screen.getByText(/this attempt was set aside/i)).toBeTruthy();
  });
});

describe("closed test", () => {
  it("renders the closed screen from data, not from an error", () => {
    mockIntro.mockReturnValue({
      data: { ...INTRO, available: false, unavailable_reason: "not_published" },
      isLoading: false,
      isError: false,
    } as never);
    mockAttempts.mockReturnValue({ data: [], isLoading: false } as never);
    mockAttempt.mockReturnValue({ data: undefined, isLoading: false } as never);
    mockResult.mockReturnValue({ data: undefined, isLoading: false } as never);
    mockStart.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    mockAdvance.mockReturnValue({ mutate: vi.fn(), isPending: false } as never);

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementFlow />
      </NextIntlClientProvider>
    );
    expect(screen.getByText(/not open yet/i)).toBeTruthy();
  });

  it("distinguishes a real fetch failure from a closed test", () => {
    mockIntro.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("network"),
    } as never);
    mockAttempts.mockReturnValue({ data: [], isLoading: false } as never);
    mockAttempt.mockReturnValue({ data: undefined, isLoading: false } as never);
    mockResult.mockReturnValue({ data: undefined, isLoading: false } as never);
    mockStart.mockReturnValue({ mutateAsync: vi.fn(), isPending: false } as never);
    mockAdvance.mockReturnValue({ mutate: vi.fn(), isPending: false } as never);

    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementFlow />
      </NextIntlClientProvider>
    );
    expect(screen.getByText(/cannot load the screener/i)).toBeTruthy();
  });
});
