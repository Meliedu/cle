import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { CourseCodeModal } from "./course-code-modal";
import {
  useCourse,
  useDeactivateEnrollCode,
  useRotateEnrollCode,
  type CourseResponse,
} from "@/hooks/use-courses";

vi.mock("@/hooks/use-courses", () => ({
  useCourse: vi.fn(),
  useRotateEnrollCode: vi.fn(),
  useDeactivateEnrollCode: vi.fn(),
}));

const mockUseCourse = vi.mocked(useCourse);
const mockUseRotate = vi.mocked(useRotateEnrollCode);
const mockUseDeactivate = vi.mocked(useDeactivateEnrollCode);

function makeCourse(overrides: Partial<CourseResponse> = {}): CourseResponse {
  return {
    id: "c1",
    name: "LANG1512",
    code: "LANG1512",
    description: null,
    language: "en",
    semester: null,
    instructor_id: "i1",
    enroll_code: "LANG1512",
    enroll_code_active: true,
    settings: {},
    setup_status: "published",
    setup_checklist: {},
    join_mode: "code",
    context_status: "approved",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderModal() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <CourseCodeModal courseId="c1" />
    </NextIntlClientProvider>
  );
}

let rotateMutate: ReturnType<typeof vi.fn>;
let deactivateMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  rotateMutate = vi.fn(async () => makeCourse({ enroll_code: "WXYZ9876" }));
  deactivateMutate = vi.fn(async () => makeCourse({ enroll_code_active: false }));
  mockUseCourse.mockReturnValue({
    data: makeCourse(),
    isLoading: false,
  } as unknown as ReturnType<typeof useCourse>);
  mockUseRotate.mockReturnValue({
    mutateAsync: rotateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useRotateEnrollCode>);
  mockUseDeactivate.mockReturnValue({
    mutateAsync: deactivateMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDeactivateEnrollCode>);
});

describe("CourseCodeModal", () => {
  it("opens the modal from the trigger and hides the code by default", async () => {
    renderModal();
    expect(screen.queryByText("LANG1512", { selector: "code" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Manage code/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reveal/i })).toBeTruthy()
    );
    // Code is still masked (raw value not in a <code> element yet).
    expect(screen.queryByText("LANG1512", { selector: "code" })).toBeNull();
  });

  it("reveals the code on click", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /Manage code/i }));
    fireEvent.click(await screen.findByRole("button", { name: /Reveal/i }));
    expect(screen.getByText("LANG1512", { selector: "code" })).toBeTruthy();
  });

  it("rotates the code through the rotate endpoint", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /Manage code/i }));
    fireEvent.click(await screen.findByRole("button", { name: /New code/i }));
    await waitFor(() => expect(rotateMutate).toHaveBeenCalledTimes(1));
  });

  it("deactivates join access through the deactivate endpoint", async () => {
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /Manage code/i }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Deactivate join access/i })
    );
    await waitFor(() => expect(deactivateMutate).toHaveBeenCalledTimes(1));
  });

  it("surfaces the join_mode read-only (approval required)", async () => {
    mockUseCourse.mockReturnValue({
      data: makeCourse({ join_mode: "code_plus_approval" }),
      isLoading: false,
    } as unknown as ReturnType<typeof useCourse>);
    renderModal();
    fireEvent.click(screen.getByRole("button", { name: /Manage code/i }));
    expect(await screen.findByText(/Approval required/i)).toBeTruthy();
  });
});
