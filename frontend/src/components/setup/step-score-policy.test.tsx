import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepScorePolicy } from "./step-score-policy";
import {
  useCreateScoreCategory,
  useDeleteScoreCategory,
  useScoreCategories,
  useSetStep,
  useUpdateScoreCategory,
  type ScoreCategory,
} from "@/hooks/use-setup";

vi.mock("@/hooks/use-setup", () => ({
  useScoreCategories: vi.fn(),
  useCreateScoreCategory: vi.fn(),
  useUpdateScoreCategory: vi.fn(),
  useDeleteScoreCategory: vi.fn(),
  useSetStep: vi.fn(),
}));

const mockUseCategories = vi.mocked(useScoreCategories);
const mockUseCreate = vi.mocked(useCreateScoreCategory);
const mockUseUpdate = vi.mocked(useUpdateScoreCategory);
const mockUseDelete = vi.mocked(useDeleteScoreCategory);
const mockUseSetStep = vi.mocked(useSetStep);

function makeCategory(overrides: Partial<ScoreCategory> = {}): ScoreCategory {
  return {
    id: "cat1",
    course_id: "c1",
    name: "Participation",
    weight: 20,
    points_pool: null,
    sort: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepScorePolicy courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let createMutate: ReturnType<typeof vi.fn>;
let updateMutate: ReturnType<typeof vi.fn>;
let deleteMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  createMutate = vi.fn(async () => makeCategory({ id: "new" }));
  updateMutate = vi.fn(async () => makeCategory());
  deleteMutate = vi.fn(async () => undefined);
  setStepMutate = vi.fn(async () => ({}));
  mockUseCategories.mockReturnValue({
    data: [makeCategory(), makeCategory({ id: "cat2", name: "Quizzes", weight: null, sort: 1 })],
    isLoading: false,
  } as unknown as ReturnType<typeof useScoreCategories>);
  mockUseCreate.mockReturnValue({
    mutateAsync: createMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateScoreCategory>);
  mockUseUpdate.mockReturnValue({
    mutateAsync: updateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateScoreCategory>);
  mockUseDelete.mockReturnValue({
    mutateAsync: deleteMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteScoreCategory>);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepScorePolicy", () => {
  it("lists the seeded score categories with their weights", () => {
    renderStep();
    expect((screen.getByDisplayValue("Participation") as HTMLInputElement).value).toBe(
      "Participation"
    );
    expect(screen.getByDisplayValue("Quizzes")).toBeTruthy();
    expect(screen.getByDisplayValue("20")).toBeTruthy();
  });

  it("adds a category via the scores API", async () => {
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /Add category/i }));
    await waitFor(() => expect(createMutate).toHaveBeenCalledTimes(1));
    const payload = createMutate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.name).toBe("New category");
  });

  it("saves an edited category name + weight through PATCH", async () => {
    renderStep();
    fireEvent.change(screen.getByDisplayValue("Participation"), {
      target: { value: "Class Participation" },
    });
    const saveButtons = screen.getAllByRole("button", { name: /^Save$/i });
    fireEvent.click(saveButtons[0]);
    await waitFor(() => expect(updateMutate).toHaveBeenCalledTimes(1));
    expect(updateMutate.mock.calls[0][0]).toMatchObject({
      id: "cat1",
      name: "Class Participation",
      weight: 20,
    });
  });

  it("removes a category via DELETE", async () => {
    renderStep();
    fireEvent.click(screen.getByRole("button", { name: /Remove Participation/i }));
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledWith("cat1"));
  });

  it("flips the score_policy flag when Save policy is pressed", async () => {
    const onComplete = vi.fn();
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /Save policy/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "score_policy", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });

  it("shows an empty state when there are no categories", () => {
    mockUseCategories.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useScoreCategories>);
    renderStep();
    expect(screen.getByText(/No score categories yet/i)).toBeTruthy();
  });
});
