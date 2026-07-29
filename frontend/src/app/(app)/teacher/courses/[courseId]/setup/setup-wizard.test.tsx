import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../../../../../messages/en.json";
import { SetupWizard } from "./setup-wizard";
import { SETUP_STEP_KEYS, useSetupState, type SetupState } from "@/hooks/use-setup";
import { useDocuments } from "@/hooks/use-documents";
import { useUrlState } from "@/hooks/use-url-state";

vi.mock("@/hooks/use-setup", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-setup")>();
  return { ...actual, useSetupState: vi.fn() };
});
vi.mock("@/hooks/use-documents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-documents")>();
  return { ...actual, useDocuments: vi.fn(), useReprocessDocument: vi.fn() };
});
vi.mock("@/hooks/use-url-state", () => ({ useUrlState: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

// Stage bodies have their own suites; stub them so this suite is about the
// five-stage shell, not the nine step forms inside it.
vi.mock("@/components/setup/stage-basics", () => ({
  StageBasics: () => <div data-testid="stage-body">basics body</div>,
}));
vi.mock("@/components/setup/stage-sources", () => ({
  StageSources: () => <div data-testid="stage-body">sources body</div>,
}));
vi.mock("@/components/setup/stage-schedule", () => ({
  StageSchedule: () => <div data-testid="stage-body">schedule body</div>,
}));
vi.mock("@/components/setup/stage-review", () => ({
  StageReview: () => <div data-testid="stage-body">review body</div>,
}));
vi.mock("@/components/setup/stage-publish", () => ({
  StagePublish: () => <div data-testid="stage-body">publish body</div>,
}));

const mockUseSetupState = vi.mocked(useSetupState);
const mockUseDocuments = vi.mocked(useDocuments);
const mockUseUrlState = vi.mocked(useUrlState);

function stubUrlState(initial: Record<string, string> = {}) {
  const params = new URLSearchParams(initial);
  const set = vi.fn();
  mockUseUrlState.mockReturnValue({
    get: (key: string, fallback = "") => params.get(key) ?? fallback,
    set,
    setMany: vi.fn(),
    clear: vi.fn(),
    search: params.toString(),
  });
  return { set };
}

function stubState(done: readonly string[], overrides: Partial<SetupState> = {}) {
  const steps: Record<string, boolean> = {};
  for (const key of SETUP_STEP_KEYS) steps[key] = done.includes(key);
  mockUseSetupState.mockReturnValue({
    data: {
      setup_status: "draft",
      context_status: "draft",
      steps,
      missing: SETUP_STEP_KEYS.filter((key) => !done.includes(key)),
      ...overrides,
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useSetupState>);
}

function stubDocuments(
  docs: readonly {
    id: string;
    filename: string;
    status: string;
    error_code?: string;
  }[] = []
) {
  mockUseDocuments.mockReturnValue({
    data: docs,
    isLoading: false,
  } as unknown as ReturnType<typeof useDocuments>);
}

function renderWizard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <SetupWizard courseId="c1" />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);
beforeEach(() => {
  vi.clearAllMocks();
  stubUrlState();
  stubState([]);
  stubDocuments();
});

describe("SetupWizard: five user-facing stages (Plate 05, rule 1)", () => {
  it("renders exactly five stages, not ten steps", () => {
    renderWizard();
    const stepper = screen.getByRole("navigation", {
      name: "Course setup stages",
    });
    const stages = within(stepper).getAllByRole("button");
    expect(stages).toHaveLength(5);
  });

  it("names the five approved stages in order", () => {
    stubState([...SETUP_STEP_KEYS]);
    renderWizard();
    const stepper = screen.getByRole("navigation", {
      name: "Course setup stages",
    });
    for (const label of ["Basics", "Sources", "Schedule", "Review", "Publish"]) {
      expect(within(stepper).getByText(label)).toBeTruthy();
    }
  });

  it("keeps sub-step granularity visible inside a stage", () => {
    // Sources owns three backend steps; one of them is done.
    stubState(["basics", "syllabus"]);
    stubUrlState({ stage: "sources" });
    renderWizard();
    expect(screen.getByText("1 of 3 done")).toBeTruthy();
  });

  it("promotes no backend step name to a top-level stage", () => {
    renderWizard();
    const stepper = screen.getByRole("navigation", {
      name: "Course setup stages",
    });
    for (const hidden of [
      "Syllabus",
      "Analyzer review",
      "Score policy",
      "Class code",
      "Learning outcomes",
    ]) {
      expect(within(stepper).queryByText(hidden)).toBeNull();
    }
  });

  it("lands on the first incomplete stage", () => {
    stubState(["basics"]);
    renderWizard();
    expect(screen.getByTestId("stage-body").textContent).toBe("sources body");
  });

  it("keeps the selected stage in URL state so refresh and Back agree", () => {
    stubState(["basics"]);
    const { set } = stubUrlState({ stage: "sources" });
    renderWizard();
    fireEvent.click(screen.getByRole("button", { name: /^Basics/ }));
    expect(set).toHaveBeenCalledWith("stage", "basics");
  });
});

describe("SetupWizard: stage reachability", () => {
  it("locks stages beyond the frontier and explains why", () => {
    renderWizard();
    const review = screen.getByRole("button", { name: /Review opens after/ });
    // aria-disabled, not `disabled`: a locked stage must stay in the tab
    // order so its "why is this locked" label is reachable.
    expect(review.getAttribute("aria-disabled")).toBe("true");
  });

  it("opens a stage the user has reached", () => {
    stubState(["basics"]);
    renderWizard();
    expect(
      screen.getByRole("button", { name: /^Sources/ }).getAttribute("aria-disabled")
    ).toBe("false");
  });

  it("keeps Publish closed while any step is missing", () => {
    stubState(["basics", "syllabus", "materials", "analyzer_review", "schedule"]);
    renderWizard();
    expect(
      screen
        .getByRole("button", { name: /Publish opens after/ })
        .getAttribute("aria-disabled")
    ).toBe("true");
  });

  it("opens Publish once nothing is missing", () => {
    stubState([...SETUP_STEP_KEYS]);
    renderWizard();
    expect(
      screen.getByRole("button", { name: /^Publish/ }).getAttribute("aria-disabled")
    ).toBe("false");
  });

  it("refuses a deep link to a locked stage", () => {
    // Disabling the stepper button does not gate the ROUTE. Typing
    // `?stage=publish` on a brand-new course used to render the publish screen
    // with every prerequisite still outstanding.
    stubState([]);
    stubUrlState({ stage: "publish" });
    renderWizard();
    expect(screen.getByTestId("stage-body").textContent).toBe("basics body");
  });

  it("honours a deep link to a stage the user has reached", () => {
    stubState(["basics"]);
    stubUrlState({ stage: "sources" });
    renderWizard();
    expect(screen.getByTestId("stage-body").textContent).toBe("sources body");
  });

  it("falls back to the frontier rather than erroring on a bad stage value", () => {
    stubState(["basics"]);
    stubUrlState({ stage: "not-a-stage" });
    renderWizard();
    expect(screen.getByTestId("stage-body").textContent).toBe("sources body");
  });
});

describe("SetupWizard: safe exit and provenance (rules 2 and 4)", () => {
  it("keeps global context and a safe exit, and nothing else", () => {
    renderWizard();
    expect(
      screen.getByRole("link", { name: /Courses/ }).getAttribute("href")
    ).toBe("/teacher/courses");
    expect(screen.getByRole("button", { name: "Save and leave" })).toBeTruthy();
  });

  it("states that processing survives leaving the page", () => {
    renderWizard();
    expect(
      screen.getAllByText(
        "Processing continues safely if you leave this page."
      ).length
    ).toBeGreaterThan(0);
  });

  it("shows provenance for each source", () => {
    stubDocuments([
      { id: "d1", filename: "Course syllabus.pdf", status: "completed" },
      { id: "d2", filename: "Week 1 reading.pdf", status: "processing" },
    ]);
    renderWizard();

    const rail = screen.getByRole("region", { name: "Source provenance" });
    expect(within(rail).getByText("Course syllabus.pdf")).toBeTruthy();
    expect(within(rail).getByText("Grounded")).toBeTruthy();
    expect(within(rail).getByText("Week 1 reading.pdf")).toBeTruthy();
    expect(within(rail).getByText("Processing")).toBeTruthy();
  });

  it("summarises safe-to-leave state in words", () => {
    stubDocuments([
      { id: "d1", filename: "a.pdf", status: "completed" },
      { id: "d2", filename: "b.pdf", status: "processing" },
      {
        id: "d3",
        filename: "c.pdf",
        status: "failed",
        error_code: "unreadable_file",
      },
    ]);
    renderWizard();

    const rail = screen.getByRole("region", { name: "Safe to leave" });
    expect(within(rail).getByText("1 source processing")).toBeTruthy();
    expect(within(rail).getByText("1 source needs attention")).toBeTruthy();
    expect(within(rail).getByText("1 source ready")).toBeTruthy();
    // The badge repeats the state as a word, not only as a tint.
    expect(within(rail).getByText("Warning")).toBeTruthy();
  });

  it("says the provenance panel is empty rather than rendering nothing", () => {
    renderWizard();
    expect(screen.getByText("No sources added yet.")).toBeTruthy();
  });
});
