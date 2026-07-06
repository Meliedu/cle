import { cleanup, render } from "@testing-library/react";
import { Sparkles } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";
import { PageHeader } from "./page-header";
import { StateBanner } from "./state-banner";
import type { StateTone } from "./tones";

afterEach(cleanup);

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

  it("marks the waiting tone with aria-live=polite", () => {
    const { getByRole } = render(
      <StateBanner tone="waiting" title="Generating quiz" />
    );

    expect(getByRole("status").getAttribute("aria-live")).toBe("polite");
  });

  it("uses role=alert for warning and blocked tones", () => {
    const warning = render(<StateBanner tone="warning" title="Heads up" />);
    expect(
      warning.container.querySelector('[role="alert"]')?.getAttribute("data-tone")
    ).toBe("warning");

    const blocked = render(<StateBanner tone="blocked" title="Locked" />);
    expect(
      blocked.container.querySelector('[role="alert"]')?.getAttribute("data-tone")
    ).toBe("blocked");
  });

  it("passes arbitrary HTML attributes through to the root", () => {
    const { getByTestId } = render(
      <StateBanner tone="info" title="Hello" data-testid="banner-root" />
    );

    expect(getByTestId("banner-root").getAttribute("role")).toBe("status");
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

  it("defaults the empty variant to the Inbox icon", () => {
    const { container } = render(<EmptyState title="No documents" />);

    const root = container.querySelector('[data-variant="empty"]');
    expect(root?.querySelector(".lucide-inbox")).toBeTruthy();
  });

  it("respects a custom icon override and renders the action slot", () => {
    const { container, getByText } = render(
      <EmptyState
        title="No flashcards"
        icon={Sparkles}
        action={<button>Create deck</button>}
      />
    );

    expect(container.querySelector(".lucide-sparkles")).toBeTruthy();
    expect(container.querySelector(".lucide-inbox")).toBeFalsy();
    expect(getByText("Create deck")).toBeTruthy();
  });

  it("passes arbitrary HTML attributes through to the root", () => {
    const { getByTestId } = render(
      <EmptyState title="Empty" data-testid="empty-root" />
    );

    expect(getByTestId("empty-root").getAttribute("data-variant")).toBe(
      "empty"
    );
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

  it("renders description and breadcrumb slots", () => {
    const { getByText } = render(
      <PageHeader
        title="COMP 1021"
        description="Introduction to Computer Science."
        breadcrumb={<a href="/dashboard">Dashboard</a>}
      />
    );

    expect(getByText("Introduction to Computer Science.")).toBeTruthy();
    expect(getByText("Dashboard").getAttribute("href")).toBe("/dashboard");
  });

  it("respects as=h2 and renders no h1", () => {
    const { container, getByRole } = render(
      <PageHeader title="Section" as="h2" />
    );

    expect(getByRole("heading", { level: 2 }).textContent).toBe("Section");
    expect(container.querySelector("h1")).toBeFalsy();
  });

  it("passes arbitrary HTML attributes through to the root header", () => {
    const { getByTestId } = render(
      <PageHeader title="Courses" data-testid="header-root" />
    );

    expect(getByTestId("header-root").tagName).toBe("HEADER");
  });
});
