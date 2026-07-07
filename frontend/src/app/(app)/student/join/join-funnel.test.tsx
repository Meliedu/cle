import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../../../messages/en.json";
import { JoinFunnel } from "./join-funnel";
import { useLookupCode, type CourseLookup } from "@/hooks/use-enrollment";
import { ApiError } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-enrollment", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/use-enrollment")>();
  return { ...actual, useLookupCode: vi.fn() };
});

const mockUseLookupCode = vi.mocked(useLookupCode);

function makeLookup(overrides: Partial<CourseLookup> = {}): CourseLookup {
  return {
    course_id: "course-1",
    name: "LANG1511",
    is_open: true,
    join_mode: "code",
    code_active: true,
    ...overrides,
  };
}

function stubLookup(
  impl: (code: string) => Promise<CourseLookup>,
  isPending = false
) {
  const mutateAsync = vi.fn(impl);
  mockUseLookupCode.mockReturnValue({
    mutateAsync,
    isPending,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useLookupCode>);
  return mutateAsync;
}

function renderFunnel() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <JoinFunnel />
    </NextIntlClientProvider>
  );
}

function submitCode(value: string) {
  const input = screen.getByLabelText("Course code");
  fireEvent.change(input, { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Join course" }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("JoinFunnel — S003 code entry", () => {
  it("blocks submit on a code that is not 8 characters", () => {
    const mutateAsync = stubLookup(async () => makeLookup());
    renderFunnel();

    submitCode("ABC");

    expect(mutateAsync).not.toHaveBeenCalled();
    expect(
      screen.getByText("Enrollment codes are 8 characters.")
    ).toBeTruthy();
  });

  it("advances a valid, active code to the preview step", async () => {
    const mutateAsync = stubLookup(async () => makeLookup());
    renderFunnel();

    submitCode("abcd2345");

    await waitFor(() =>
      expect(screen.getByText("Course preview")).toBeTruthy()
    );
    // Normalized to uppercase before lookup.
    expect(mutateAsync).toHaveBeenCalledWith("ABCD2345");
    expect(push).not.toHaveBeenCalled();
  });

  it("branches a deactivated code to S004 (inactive)", async () => {
    stubLookup(async () => makeLookup({ code_active: false }));
    renderFunnel();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );
    expect(
      screen.getByText(/no longer active/i)
    ).toBeTruthy();
  });

  it("branches an unknown code (404) to S004 (not found)", async () => {
    stubLookup(async () => {
      throw new ApiError(404, "not found");
    });
    renderFunnel();

    submitCode("ZZZZ9999");

    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );
    expect(screen.getByText(/couldn't find a course/i)).toBeTruthy();
  });

  it("shows an inline retry message on a non-branch error, staying on S003", async () => {
    stubLookup(async () => {
      throw new ApiError(500, "boom");
    });
    renderFunnel();

    submitCode("ABCD2345");

    await waitFor(() =>
      expect(
        screen.getByText("We couldn't check that code. Please try again.")
      ).toBeTruthy()
    );
    // Still on the code step.
    expect(screen.getByLabelText("Course code")).toBeTruthy();
  });

  it("returns to S003 from S004 via try again", async () => {
    stubLookup(async () => makeLookup({ code_active: false }));
    renderFunnel();

    submitCode("ABCD2345");
    await waitFor(() =>
      expect(
        screen.getByText("This code is invalid or inactive")
      ).toBeTruthy()
    );

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByLabelText("Course code")).toBeTruthy();
  });
});
