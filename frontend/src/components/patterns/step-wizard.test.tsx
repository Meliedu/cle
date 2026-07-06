import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StepWizard, stepStatus, type WizardStep } from "./step-wizard";

afterEach(cleanup);

const steps: WizardStep[] = [
  { id: "basics", label: "Basics", complete: true },
  { id: "syllabus", label: "Syllabus", complete: false },
  { id: "publish", label: "Publish", complete: false, blocked: true },
];

describe("stepStatus", () => {
  it("prioritizes the current step over completion", () => {
    expect(stepStatus({ id: "a", label: "A", complete: true }, "a")).toBe(
      "current"
    );
  });

  it("derives complete / blocked / upcoming", () => {
    expect(stepStatus({ id: "a", label: "A", complete: true }, "b")).toBe(
      "complete"
    );
    expect(
      stepStatus({ id: "a", label: "A", complete: false, blocked: true }, "b")
    ).toBe("blocked");
    expect(stepStatus({ id: "a", label: "A", complete: false }, "b")).toBe(
      "upcoming"
    );
  });
});

describe("StepWizard", () => {
  it("marks completed steps and highlights the current one", () => {
    render(
      <StepWizard steps={steps} currentId="syllabus">
        body
      </StepWizard>
    );
    expect(
      screen.getByRole("listitem", { name: /Basics/ }).getAttribute("data-status")
    ).toBe("complete");
    expect(
      screen
        .getByRole("listitem", { name: /Syllabus/ })
        .getAttribute("data-status")
    ).toBe("current");
    expect(
      screen.getByRole("listitem", { name: /Publish/ }).getAttribute("data-status")
    ).toBe("blocked");
    expect(screen.getByText("body")).toBeTruthy();
  });

  it("sets aria-current=step only on the active rail step", () => {
    render(
      <StepWizard steps={steps} currentId="syllabus">
        body
      </StepWizard>
    );
    expect(
      screen.getByRole("listitem", { name: /Syllabus/ }).getAttribute("aria-current")
    ).toBe("step");
    expect(
      screen.getByRole("listitem", { name: /Basics/ }).getAttribute("aria-current")
    ).toBeNull();
  });

  it("only makes complete/current steps clickable and cannot jump ahead", () => {
    const onStepSelect = vi.fn();
    render(
      <StepWizard steps={steps} currentId="syllabus" onStepSelect={onStepSelect}>
        body
      </StepWizard>
    );
    // The complete step is a button.
    fireEvent.click(screen.getByRole("button", { name: /Basics/ }));
    expect(onStepSelect).toHaveBeenCalledWith("basics");
    // The blocked (ahead) step is not interactive.
    expect(screen.queryByRole("button", { name: /Publish/ })).toBeNull();
  });

  it("disables Back on the first step", () => {
    render(
      <StepWizard steps={steps} currentId="basics" onBack={vi.fn()} onNext={vi.fn()}>
        body
      </StepWizard>
    );
    expect(
      (screen.getByRole("button", { name: /Back/ }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: /Next/ }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("disables Next on the last step", () => {
    render(
      <StepWizard steps={steps} currentId="publish" onBack={vi.fn()} onNext={vi.fn()}>
        body
      </StepWizard>
    );
    expect(
      (screen.getByRole("button", { name: /Next/ }) as HTMLButtonElement).disabled
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: /Back/ }) as HTMLButtonElement).disabled
    ).toBe(false);
  });

  it("renders a progress indicator reflecting the current position", () => {
    render(
      <StepWizard steps={steps} currentId="syllabus">
        body
      </StepWizard>
    );
    expect(screen.getByText("Step 2 of 3")).toBeTruthy();
    expect(
      screen.getByRole("progressbar").getAttribute("aria-valuenow")
    ).toBe("2");
  });

  it("shows the Save control only when onSave is provided", () => {
    const { rerender } = render(
      <StepWizard steps={steps} currentId="syllabus">
        body
      </StepWizard>
    );
    expect(screen.queryByRole("button", { name: /Save/ })).toBeNull();

    rerender(
      <StepWizard steps={steps} currentId="syllabus" onSave={vi.fn()} isSaving>
        body
      </StepWizard>
    );
    expect(
      (screen.getByRole("button", { name: /Save/ }) as HTMLButtonElement).disabled
    ).toBe(true);
  });
});
