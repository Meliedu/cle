import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { LearningProfileView } from "./learning-profile";
import {
  useLearningProfile,
  type LearningProfile,
  type ConceptMasteryEntry,
} from "@/hooks/use-insights";

vi.mock("@/hooks/use-insights", () => ({
  useLearningProfile: vi.fn(),
}));

const mockUseProfile = vi.mocked(useLearningProfile);

function concept(overrides: Partial<ConceptMasteryEntry>): ConceptMasteryEntry {
  return {
    concept_id: "c-1",
    concept_name: "Past tense",
    mastery_score: 0.82,
    confidence: 0.7,
    attempt_count: 5,
    last_attempt_at: "2026-07-01T10:00:00Z",
    ...overrides,
  };
}

const DISCLAIMER =
  "These are early signals from your practice, not a formal grade.";

function wrap(node: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="UTC">
      {node}
    </NextIntlClientProvider>
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe("LearningProfileView — S062 / S070", () => {
  it("renders the designed no-evidence state with the disclaimer verbatim", () => {
    mockUseProfile.mockReturnValue({
      data: {
        course_id: "course-1",
        has_evidence: false,
        concept_count: 0,
        groups: { strong: [], developing: [], weak: [] },
        disclaimer: DISCLAIMER,
      } satisfies LearningProfile,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useLearningProfile>);

    wrap(<LearningProfileView courseId="course-1" />);

    // Designed waiting/no-evidence EmptyState, plus the disclaimer verbatim.
    expect(screen.getByText("No profile yet")).toBeTruthy();
    expect(screen.getByText(DISCLAIMER)).toBeTruthy();
    // No concept groups rendered.
    expect(screen.queryByText("Strong")).toBeNull();
  });

  it("groups concepts and expands a concept's evidence panel on click", () => {
    mockUseProfile.mockReturnValue({
      data: {
        course_id: "course-1",
        has_evidence: true,
        concept_count: 2,
        groups: {
          strong: [concept({ concept_id: "c-strong", concept_name: "Greetings" })],
          developing: [],
          weak: [
            concept({
              concept_id: "c-weak",
              concept_name: "Subjunctive",
              mastery_score: 0.3,
            }),
          ],
        },
        disclaimer: DISCLAIMER,
      } satisfies LearningProfile,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useLearningProfile>);

    wrap(<LearningProfileView courseId="course-1" />);

    expect(screen.getByText("Strong")).toBeTruthy();
    expect(screen.getByText("Needs work")).toBeTruthy();
    expect(screen.getByText("Greetings")).toBeTruthy();

    // Evidence panel is collapsed until the concept is opened.
    expect(screen.queryByText("Confidence")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Greetings/ }));
    expect(screen.getByText("Confidence")).toBeTruthy();
    expect(screen.getByText("Mastery")).toBeTruthy();
  });
});
