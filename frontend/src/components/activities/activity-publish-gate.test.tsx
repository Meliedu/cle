import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import { ActivityPublishGate } from "./activity-publish-gate";
import { ScorePolicyError } from "@/hooks/use-quizzes";
import { ApiError } from "@/lib/api";

function renderGate(error: unknown) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ActivityPublishGate error={error} />
    </NextIntlClientProvider>
  );
}

afterEach(cleanup);

describe("ActivityPublishGate", () => {
  it("renders nothing when there is no error", () => {
    const { container } = renderGate(null);
    expect(container.firstChild).toBeNull();
  });

  it("renders a LOCALIZED deadline label for missing:['deadline']", () => {
    // Regression: the backend `SCORE_POLICY_INCOMPLETE.missing[]` vocabulary
    // emits a SINGLE `deadline` entry (never `due_at`/`close_at`/`late_rule`),
    // so the gate must translate `deadline` rather than leak the raw code.
    renderGate(new ScorePolicyError("Score policy incomplete.", ["deadline"]));

    expect(screen.getByText(/Finish the score policy to publish/)).toBeTruthy();
    // The interpolated reason names the localized field, not the raw enum id.
    expect(screen.getByText(/deadline/)).toBeTruthy();
    expect(screen.queryByText(/due_at|close_at|late_rule/)).toBeNull();
  });

  it("localizes every required score field in the reason", () => {
    renderGate(
      new ScorePolicyError("Score policy incomplete.", [
        "score_category_id",
        "points",
        "grading_mode",
        "deadline",
      ])
    );

    const reason = screen.getByText(/score category, points, grading mode, deadline/);
    expect(reason).toBeTruthy();
  });

  it("defaults to the score category field when missing[] is empty", () => {
    renderGate(new ScorePolicyError("Score policy incomplete.", []));
    expect(screen.getByText(/score category/)).toBeTruthy();
  });

  it("falls back to the raw id only for an unknown field", () => {
    renderGate(new ScorePolicyError("Score policy incomplete.", ["mystery"]));
    expect(screen.getByText(/mystery/)).toBeTruthy();
  });

  it("renders the config-invalid banner for ACTIVITY_CONFIG_INVALID", () => {
    renderGate(
      new ApiError(422, "bad config", "bad config", "ACTIVITY_CONFIG_INVALID")
    );
    expect(screen.getByText(/Activity setup is incomplete/)).toBeTruthy();
  });

  it("renders the not-publishable banner for ACTIVITY_NOT_PUBLISHABLE", () => {
    renderGate(
      new ApiError(409, "nope", "nope", "ACTIVITY_NOT_PUBLISHABLE")
    );
    expect(screen.getByText(/This activity can't be published/)).toBeTruthy();
  });
});
