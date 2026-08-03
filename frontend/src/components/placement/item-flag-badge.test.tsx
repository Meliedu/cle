import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it } from "vitest";

import messages from "../../../messages/en.json";
import type { PlacementTeacherFlag } from "@/hooks/use-placement";
import { ItemFlagBadge } from "./placement-attempt-review";

afterEach(cleanup);

function renderBadge(
  flags: readonly PlacementTeacherFlag[],
  review?: Parameters<typeof ItemFlagBadge>[0]["review"]
) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <ItemFlagBadge flags={flags} review={review} />
    </NextIntlClientProvider>
  );
}

const BLOCKING: PlacementTeacherFlag = {
  code: "key_disputed",
  detail: "two options are defensible",
  severity: "blocking",
};

const ADVISORY: PlacementTeacherFlag = {
  code: "teacher_feedback_incorporated",
  detail: "v1.2 feedback incorporated",
  severity: "advisory",
};

describe("ItemFlagBadge", () => {
  it("renders nothing when the item carries no content note", () => {
    const { container } = renderBadge([]);
    expect(container.textContent).toBe("");
  });

  it("labels a disputed key differently from a revision to confirm", () => {
    renderBadge([BLOCKING]);
    expect(screen.getByText("Disputed")).toBeTruthy();
    cleanup();

    renderBadge([ADVISORY]);
    expect(screen.getByText("To confirm")).toBeTruthy();
  });

  it("distinguishes the two by words, not colour alone", () => {
    // The a11y bar this file already holds itself to: a reviewer who cannot
    // see the tint must still be able to tell the two states apart.
    renderBadge([BLOCKING]);
    const blocking = screen.getByText("Disputed").textContent;
    cleanup();
    renderBadge([ADVISORY]);
    expect(screen.getByText("To confirm").textContent).not.toBe(blocking);
  });

  it("treats a flag with no severity as blocking", () => {
    // Attempts scored before severity was resolved server-side have flags
    // without the field. The safe reading of an unknown defect is the serious
    // one, so it must not silently downgrade to advisory.
    renderBadge([{ code: "key_not_in_options", detail: "key D is not offered" }]);
    expect(screen.getByText("Disputed")).toBeTruthy();
  });

  it("reports the highest severity present when an item carries both", () => {
    renderBadge([ADVISORY, BLOCKING]);
    expect(screen.getByText("Disputed")).toBeTruthy();
    expect(screen.queryByText("To confirm")).toBeNull();
  });

  it("exposes the detail to assistive technology, not only on hover", () => {
    const { container } = renderBadge([ADVISORY]);
    expect(container.textContent).toContain("v1.2 feedback incorporated");
  });

  it("adds the content owner's own review question to the detail", () => {
    const { container } = renderBadge([ADVISORY], {
      review_question: "Confirm the revision retains one defensible key.",
    });
    expect(container.textContent).toContain(
      "Confirm the revision retains one defensible key."
    );
  });
});
