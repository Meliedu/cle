import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ActivityBuilder } from "./activity-builder";
import { ActivityPublishGate } from "./activity-publish-gate";
import type { Activity } from "@/hooks/use-activities";
import {
  useCreateActivity,
  usePublishActivity,
  useUpdateActivity,
} from "@/hooks/use-activities";
import { useScoreCategories } from "@/hooks/use-setup";
import { ScorePolicyError } from "@/hooks/use-quizzes";
import { ApiError } from "@/lib/api";

vi.mock("@/hooks/use-activities", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-activities")>();
  return {
    ...actual,
    useCreateActivity: vi.fn(),
    useUpdateActivity: vi.fn(),
    usePublishActivity: vi.fn(),
  };
});

vi.mock("@/hooks/use-setup", () => ({
  useScoreCategories: vi.fn(),
}));

const fakeActivity: Activity = {
  id: "act-1",
  course_id: "c1",
  meeting_id: null,
  format: "swipe",
  title: "Warm-up",
  config: { prompts: ["Agree"] },
  status: "draft",
  open_at: null,
  due_at: null,
  close_at: null,
  anonymous: false,
  score_category_id: null,
  points: null,
  grading_mode: null,
  late_rule: null,
  score_bearing: false,
  created_at: "2026-07-08T00:00:00Z",
  updated_at: "2026-07-08T00:00:00Z",
};

const createMutate = vi.fn().mockResolvedValue(fakeActivity);
const updateMutate = vi.fn().mockResolvedValue(fakeActivity);
const publishMutate = vi.fn().mockResolvedValue(fakeActivity);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useCreateActivity).mockReturnValue({
    mutateAsync: createMutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useCreateActivity>);
  vi.mocked(useUpdateActivity).mockReturnValue({
    mutateAsync: updateMutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useUpdateActivity>);
  vi.mocked(usePublishActivity).mockReturnValue({
    mutateAsync: publishMutate,
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof usePublishActivity>);
  vi.mocked(useScoreCategories).mockReturnValue({
    data: [],
    isError: false,
  } as unknown as ReturnType<typeof useScoreCategories>);
});

afterEach(cleanup);

function renderBuilder() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ActivityBuilder courseId="c1" format="swipe" />
    </NextIntlClientProvider>
  );
}

describe("ActivityBuilder", () => {
  it("writes the swipe prompt into config on save", async () => {
    renderBuilder();

    fireEvent.change(
      screen.getByPlaceholderText("e.g. Warm-up: agree or disagree?"),
      { target: { value: "Warm-up" } }
    );
    fireEvent.change(screen.getByPlaceholderText("Add a prompt…"), {
      target: { value: "Agree" },
    });
    fireEvent.click(screen.getByText("Add"));
    fireEvent.click(screen.getByText("Save draft"));

    // create mutation invoked with the format + the config array it edits
    expect(createMutate).toHaveBeenCalledTimes(1);
    const payload = createMutate.mock.calls[0][0];
    expect(payload.format).toBe("swipe");
    expect((payload.config as { prompts: string[] }).prompts).toEqual(["Agree"]);
    expect(payload.title).toBe("Warm-up");
  });
});

describe("ActivityPublishGate", () => {
  function renderGate(error: unknown) {
    return render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <ActivityPublishGate error={error} />
      </NextIntlClientProvider>
    );
  }

  it("lists missing score fields for a ScorePolicyError", () => {
    renderGate(new ScorePolicyError("incomplete", ["points", "grading_mode"]));
    expect(screen.getByText("Finish the score policy to publish")).toBeTruthy();
    expect(
      screen.getByText(/points, grading mode/)
    ).toBeTruthy();
  });

  it("renders the config-invalid state for ACTIVITY_CONFIG_INVALID", () => {
    renderGate(
      new ApiError(422, "bad", "bad", "ACTIVITY_CONFIG_INVALID")
    );
    expect(screen.getByText("Activity setup is incomplete")).toBeTruthy();
  });

  it("renders nothing when there is no error", () => {
    const { container } = renderGate(null);
    expect(container.textContent).toBe("");
  });
});
