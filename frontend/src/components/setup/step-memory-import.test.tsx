import { cleanup, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { StepMemoryImport } from "./step-memory-import";

function renderStub(onSkip = vi.fn()) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <StepMemoryImport onSkip={onSkip} />
    </NextIntlClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

describe("StepMemoryImport", () => {
  it("renders nothing when the feature flag is not enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_MEMORY_IMPORT", "");
    const { container } = renderStub();
    expect(container.firstChild).toBeNull();
  });

  it("renders the P7 stub when the feature flag is enabled", () => {
    vi.stubEnv("NEXT_PUBLIC_MEMORY_IMPORT", "enabled");
    renderStub();
    expect(screen.getByText(/Previous course memory/i)).toBeTruthy();
    expect(screen.getByText(/coming later/i)).toBeTruthy();
    expect(screen.getByText(/Coming in P7/i)).toBeTruthy();
  });

  it("does not gate publishing — offers a skip action only", () => {
    vi.stubEnv("NEXT_PUBLIC_MEMORY_IMPORT", "enabled");
    const onSkip = vi.fn();
    renderStub(onSkip);
    const skip = screen.getByRole("button", { name: /Skip for now/i });
    skip.click();
    expect(onSkip).toHaveBeenCalledTimes(1);
  });
});
