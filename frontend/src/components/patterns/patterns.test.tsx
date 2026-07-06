import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";
import { PageHeader } from "./page-header";
import { StateBanner, type StateTone } from "./state-banner";

describe("StateBanner", () => {
  it("renders title + reason and exposes role=status", () => {
    const { getByRole, getByText } = render(
      <StateBanner
        tone="info"
        title="Upload received"
        reason="We are processing your file."
      />
    );

    const banner = getByRole("status");
    expect(banner.getAttribute("data-tone")).toBe("info");
    expect(getByText("Upload received")).toBeTruthy();
    expect(getByText("We are processing your file.")).toBeTruthy();
  });

  it("renders the mapped icon for every tone", () => {
    const cases: ReadonlyArray<readonly [StateTone, string]> = [
      ["info", "lucide-info"],
      ["waiting", "lucide-clock"],
      ["warning", "lucide-triangle-alert"],
      ["blocked", "lucide-lock"],
      ["success", "lucide-circle-check"],
    ];

    for (const [tone, iconClass] of cases) {
      const { container } = render(<StateBanner tone={tone} title={tone} />);
      const banner = container.querySelector('[data-tone="' + tone + '"]');
      expect(banner?.querySelector("." + iconClass)).toBeTruthy();
    }
  });
});

describe("EmptyState", () => {
  it("defaults the waiting variant to the Clock icon", () => {
    const { container } = render(
      <EmptyState variant="waiting" title="Nothing here yet" />
    );

    const root = container.querySelector('[data-variant="waiting"]');
    expect(root?.querySelector(".lucide-clock")).toBeTruthy();
  });
});

describe("PageHeader", () => {
  it("renders an h1 title and the actions slot", () => {
    const { getByRole, getByText } = render(
      <PageHeader title="Courses" actions={<button>New course</button>} />
    );

    expect(getByRole("heading", { level: 1 }).textContent).toBe("Courses");
    expect(getByText("New course")).toBeTruthy();
  });
});
