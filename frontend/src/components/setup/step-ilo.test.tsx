import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepIlo } from "./step-ilo";
import {
  useCreateObjective,
  useDeleteObjective,
  useObjectiveConcepts,
  useObjectives,
  useUpdateObjective,
  type Objective,
} from "@/hooks/use-objectives";
import { useSetStep } from "@/hooks/use-setup";

vi.mock("@/hooks/use-objectives", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-objectives")>();
  return {
    ...actual,
    useObjectives: vi.fn(),
    useCreateObjective: vi.fn(),
    useUpdateObjective: vi.fn(),
    useDeleteObjective: vi.fn(),
    useObjectiveConcepts: vi.fn(),
  };
});

vi.mock("@/hooks/use-setup", () => ({
  useSetStep: vi.fn(),
}));

const mockUseObjectives = vi.mocked(useObjectives);
const mockUseCreateObjective = vi.mocked(useCreateObjective);
const mockUseUpdateObjective = vi.mocked(useUpdateObjective);
const mockUseDeleteObjective = vi.mocked(useDeleteObjective);
const mockUseObjectiveConcepts = vi.mocked(useObjectiveConcepts);
const mockUseSetStep = vi.mocked(useSetStep);

function makeObjective(overrides: Partial<Objective> = {}): Objective {
  return {
    id: "o1",
    course_id: "c1",
    module_id: null,
    meeting_id: null,
    statement: "Order food and drinks in Mandarin",
    bloom_level: "apply",
    order_index: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderStep(onComplete = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepIlo courseId="c1" onComplete={onComplete} />
    </NextIntlClientProvider>
  );
}

let createMutate: ReturnType<typeof vi.fn>;
let setStepMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  createMutate = vi.fn(async () => makeObjective());
  setStepMutate = vi.fn(async () => ({}));
  mockUseObjectives.mockReturnValue({ data: [], isLoading: false } as unknown as ReturnType<
    typeof useObjectives
  >);
  mockUseCreateObjective.mockReturnValue({
    mutateAsync: createMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useCreateObjective>);
  mockUseUpdateObjective.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUpdateObjective>);
  mockUseDeleteObjective.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useDeleteObjective>);
  mockUseObjectiveConcepts.mockReturnValue({ data: [] } as unknown as ReturnType<
    typeof useObjectiveConcepts
  >);
  mockUseSetStep.mockReturnValue({
    mutateAsync: setStepMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useSetStep>);
});

describe("StepIlo", () => {
  it("shows the empty state with Approve disabled when there are no outcomes", () => {
    renderStep();
    expect(screen.getByText(/No learning outcomes yet/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Approve ILO map/i }) as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("lists outcomes with the Bloom badge and read-only concept chips", () => {
    mockUseObjectives.mockReturnValue({
      data: [makeObjective()],
      isLoading: false,
    } as unknown as ReturnType<typeof useObjectives>);
    mockUseObjectiveConcepts.mockReturnValue({
      data: [{ id: "k1", name: "tone sandhi" }],
    } as unknown as ReturnType<typeof useObjectiveConcepts>);
    renderStep();
    expect(screen.getByText(/Order food and drinks in Mandarin/)).toBeTruthy();
    // "Apply" also appears as a <select> option; the badge is an extra match.
    expect(screen.getAllByText(/^Apply$/).length).toBeGreaterThan(1);
    expect(screen.getByText(/tone sandhi/)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /Approve ILO map/i }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("creates an outcome via the objectives API", async () => {
    renderStep();
    fireEvent.change(screen.getByLabelText(/Outcome statement/i), {
      target: { value: "Introduce yourself in Mandarin" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Add outcome$/i }));
    await waitFor(() => expect(createMutate).toHaveBeenCalledTimes(1));
    const payload = createMutate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload.statement).toBe("Introduce yourself in Mandarin");
    expect(payload.order_index).toBe(0);
  });

  it("flips the ilo_map flag when Approve is pressed with an outcome present", async () => {
    const onComplete = vi.fn();
    mockUseObjectives.mockReturnValue({
      data: [makeObjective()],
      isLoading: false,
    } as unknown as ReturnType<typeof useObjectives>);
    renderStep(onComplete);
    fireEvent.click(screen.getByRole("button", { name: /Approve ILO map/i }));
    await waitFor(() =>
      expect(setStepMutate).toHaveBeenCalledWith({ step: "ilo_map", done: true })
    );
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
