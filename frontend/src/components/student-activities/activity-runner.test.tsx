import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ActivityRunner } from "./activity-runner";
import {
  useActivity,
  useSubmitActivityResponse,
  type Activity,
} from "@/hooks/use-activities";

vi.mock("@/hooks/use-activities", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-activities")>();
  return {
    ...actual,
    useActivity: vi.fn(),
    useSubmitActivityResponse: vi.fn(),
  };
});

const mockUseActivity = vi.mocked(useActivity);
const mockUseSubmit = vi.mocked(useSubmitActivityResponse);

function makeActivity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: "a1",
    course_id: "c1",
    meeting_id: null,
    format: "vote",
    title: "Which stance is stronger?",
    config: { options: ["Option A", "Option B"] },
    status: "live",
    open_at: null,
    due_at: null,
    close_at: null,
    anonymous: false,
    score_category_id: null,
    points: null,
    grading_mode: null,
    late_rule: null,
    score_bearing: false,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

function setActivity(
  data: Activity | undefined,
  extra: Partial<ReturnType<typeof useActivity>> = {}
) {
  mockUseActivity.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    ...extra,
  } as unknown as ReturnType<typeof useActivity>);
}

const mutateAsync = vi.fn();

function setSubmit(extra: Partial<ReturnType<typeof useSubmitActivityResponse>> = {}) {
  mockUseSubmit.mockReturnValue({
    mutateAsync,
    isPending: false,
    isError: false,
    error: null,
    ...extra,
  } as unknown as ReturnType<typeof useSubmitActivityResponse>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mutateAsync.mockResolvedValue({
    id: "r1",
    user_id: "u1",
    payload: { choice: "Option A" },
    status: "submitted",
    submitted_at: "2026-07-02T00:00:00Z",
  });
  setSubmit();
});
afterEach(cleanup);

function renderRunner() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ActivityRunner courseId="c1" activityId="a1" />
    </NextIntlClientProvider>
  );
}

describe("ActivityRunner", () => {
  it("submits the picked vote choice and shows the confirmation", async () => {
    setActivity(makeActivity());
    renderRunner();

    fireEvent.click(screen.getByText("Option A"));
    fireEvent.click(screen.getByRole("button", { name: "Submit vote" }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        payload: { choice: "Option A" },
      });
    });
    expect(await screen.findByText("Response recorded")).toBeTruthy();
  });

  it("renders the waiting state when the activity is not open", () => {
    setActivity(makeActivity({ status: "draft" }));
    renderRunner();
    expect(
      screen.getByText("Waiting for your instructor to start")
    ).toBeTruthy();
  });

  it("renders the waiting state when the read fails", () => {
    setActivity(undefined, { isError: true });
    renderRunner();
    expect(
      screen.getByText("Waiting for your instructor to start")
    ).toBeTruthy();
  });
});
