import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { IloStrengthMap } from "./ilo-strength-map";
import { SkillPatternMap } from "./skill-pattern-map";
import {
  useIloMap,
  useSkillMap,
  type StudentIloMap,
  type SkillMap,
} from "@/hooks/use-insights";

vi.mock("@/hooks/use-insights", () => ({
  useIloMap: vi.fn(),
  useSkillMap: vi.fn(),
}));

const mockUseIlo = vi.mocked(useIloMap);
const mockUseSkill = vi.mocked(useSkillMap);

function wrap(node: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe("SkillPatternMap — S065 / Decision 5", () => {
  it("renders every skill cell in the honest no-evidence state with one reason", () => {
    const skills = [
      { skill: "reading", label: "Reading", has_evidence: false, strength: null, sample_size: null },
      { skill: "speaking", label: "Speaking", has_evidence: false, strength: null, sample_size: null },
      { skill: "writing", label: "Writing", has_evidence: false, strength: null, sample_size: null },
    ] as const;

    mockUseSkill.mockReturnValue({
      data: {
        course_id: "course-1",
        has_evidence: false,
        skills,
      } as unknown as SkillMap,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useSkillMap>);

    const { container } = wrap(<SkillPatternMap courseId="course-1" />);

    // Every skill label renders...
    expect(screen.getByText("Reading")).toBeTruthy();
    expect(screen.getByText("Speaking")).toBeTruthy();
    expect(screen.getByText("Writing")).toBeTruthy();

    // ...each cell carries a no-evidence marker (one per cell + the banner title).
    expect(screen.getAllByText("No evidence yet").length).toBe(skills.length + 1);
    // The honest Decision-5 reason is shown exactly once.
    expect(
      screen.getByText(/skill-level evidence yet/)
    ).toBeTruthy();
    // No fabricated score anywhere in the grid.
    expect(container.textContent).not.toMatch(/\d+%/);
  });
});

describe("IloStrengthMap — S064 / S070", () => {
  it("shows the designed no-evidence state when no objective has evidence", () => {
    mockUseIlo.mockReturnValue({
      data: {
        course_id: "course-1",
        has_evidence: false,
        objectives: [],
      } as unknown as StudentIloMap,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useIloMap>);

    wrap(<IloStrengthMap courseId="course-1" />);
    expect(screen.getByText("No objective evidence yet")).toBeTruthy();
  });

  it("renders an honest no-evidence cell for an objective with no evidence, never a 0", () => {
    mockUseIlo.mockReturnValue({
      data: {
        course_id: "course-1",
        has_evidence: true,
        objectives: [
          {
            objective_id: "o-1",
            statement: "Order food in a cafe",
            bloom_level: "apply",
            has_evidence: true,
            strength: 0.6,
            concept_count: 2,
            evidence_concept_count: 1,
          },
          {
            objective_id: "o-2",
            statement: "Describe your weekend",
            bloom_level: null,
            has_evidence: false,
            strength: null,
            concept_count: 3,
            evidence_concept_count: 0,
          },
        ],
      } as unknown as StudentIloMap,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useIloMap>);

    wrap(<IloStrengthMap courseId="course-1" />);

    expect(screen.getByText("Order food in a cafe")).toBeTruthy();
    expect(screen.getByText("Describe your weekend")).toBeTruthy();
    // The evidence-bearing objective shows a strength meter + percentage; the
    // no-evidence objective fabricates NO 0 — only ONE progressbar exists.
    expect(screen.getByText("60%")).toBeTruthy();
    expect(screen.getAllByRole("progressbar").length).toBe(1);
    expect(screen.getByText("No evidence yet")).toBeTruthy();
  });
});
