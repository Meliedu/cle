import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { ScorePolicyBlockedBanner } from "./score-policy-blocked-banner";
import { ScorePolicyError } from "@/hooks/use-quizzes";

function renderBanner(
  missing: readonly string[],
  onJump?: (field: string) => void
) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ScorePolicyBlockedBanner
        missing={missing}
        onJump={onJump as never}
      />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

describe("ScorePolicyBlockedBanner", () => {
  it("maps a ScorePolicyError.missing[] to a blocked banner with one row per field", () => {
    // The exact shape usePublishQuiz throws on a gated graded publish.
    const err = new ScorePolicyError("Score policy incomplete.", [
      "score_category_id",
      "points",
      "grading_mode",
      "deadline",
    ]);

    renderBanner(err.missing);

    expect(screen.getByText("Finish the score policy to publish")).toBeTruthy();
    expect(screen.getByText("Score category")).toBeTruthy();
    expect(screen.getByText("Points")).toBeTruthy();
    expect(screen.getByText("Grading mode")).toBeTruthy();
    expect(screen.getByText("Deadline")).toBeTruthy();
  });

  it("filters unknown/duplicate codes so no raw enum string leaks", () => {
    renderBanner(["points", "totally_new_code"], vi.fn());

    expect(screen.getByText("Points")).toBeTruthy();
    expect(screen.queryByText("totally_new_code")).toBeNull();
    // Only the one known field row is rendered.
    expect(screen.getAllByRole("button", { name: "Fix" })).toHaveLength(1);
  });

  it("invokes onJump with the field when Fix is clicked", () => {
    const onJump = vi.fn();
    renderBanner(["grading_mode"], onJump);

    fireEvent.click(screen.getByRole("button", { name: "Fix" }));
    expect(onJump).toHaveBeenCalledWith("grading_mode");
  });
});
