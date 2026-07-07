import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { GradeExportCard } from "./grade-export-card";
import { useGradeExport } from "@/hooks/use-scores";

vi.mock("@/hooks/use-scores", () => ({
  useGradeExport: vi.fn(),
}));

const mutate = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useGradeExport).mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useGradeExport>);
});

afterEach(cleanup);

function renderCard() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <GradeExportCard courseId="c1" />
    </NextIntlClientProvider>
  );
}

describe("GradeExportCard", () => {
  it("shows the audited-export note and triggers the export on click", () => {
    renderCard();

    // the "every export is audited" disclosure is always visible
    expect(screen.getByText(/Every export is audited/)).toBeTruthy();

    fireEvent.click(screen.getByText("Export grades (CSV)"));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it("renders the error banner when the export fails", () => {
    vi.mocked(useGradeExport).mockReturnValue({
      mutate,
      isPending: false,
      isError: true,
    } as unknown as ReturnType<typeof useGradeExport>);

    renderCard();
    expect(screen.getByText("Export failed")).toBeTruthy();
  });
});
