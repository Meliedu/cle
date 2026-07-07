import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { JoinRequestApproval } from "./join-request-approval";
import {
  useApproveJoinRequest,
  useDenyJoinRequest,
  useJoinRequests,
  type JoinRequest,
} from "@/hooks/use-enrollment";
import { ApiError } from "@/lib/api";

vi.mock("@/hooks/use-enrollment", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/use-enrollment")>(
    "@/hooks/use-enrollment"
  );
  return {
    ...actual,
    useJoinRequests: vi.fn(),
    useApproveJoinRequest: vi.fn(),
    useDenyJoinRequest: vi.fn(),
  };
});

const mockUseJoinRequests = vi.mocked(useJoinRequests);
const mockUseApprove = vi.mocked(useApproveJoinRequest);
const mockUseDeny = vi.mocked(useDenyJoinRequest);

function makeRequest(overrides: Partial<JoinRequest> = {}): JoinRequest {
  return {
    enrollment_id: "e1",
    user_id: "u1",
    full_name: "Jamie Park",
    email: "jamie@connect.ust.hk",
    requested_at: "2026-01-10T00:00:00Z",
    status: "pending",
    ...overrides,
  };
}

function renderList() {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <JoinRequestApproval courseId="c1" />
    </NextIntlClientProvider>
  );
}

let approveMutate: ReturnType<typeof vi.fn>;
let denyMutate: ReturnType<typeof vi.fn>;

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  approveMutate = vi.fn(async () => makeRequest({ status: "active" }));
  denyMutate = vi.fn(async () => makeRequest({ status: "rejected" }));
  mockUseJoinRequests.mockReturnValue({
    data: [makeRequest(), makeRequest({ enrollment_id: "e2", full_name: "Chase Li", email: "chase@connect.ust.hk" })],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useJoinRequests>);
  mockUseApprove.mockReturnValue({
    mutateAsync: approveMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useApproveJoinRequest>);
  mockUseDeny.mockReturnValue({
    mutateAsync: denyMutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDenyJoinRequest>);
});

describe("JoinRequestApproval", () => {
  it("lists the pending requests", () => {
    renderList();
    expect(screen.getByText("Jamie Park")).toBeTruthy();
    expect(screen.getByText("Chase Li")).toBeTruthy();
  });

  it("approves a request through the approve mutation", async () => {
    renderList();
    fireEvent.click(screen.getAllByRole("button", { name: /Approve/i })[0]);
    await waitFor(() => expect(approveMutate).toHaveBeenCalledWith("e1"));
  });

  it("denies a request through the deny mutation", async () => {
    renderList();
    fireEvent.click(screen.getAllByRole("button", { name: /Deny/i })[0]);
    await waitFor(() => expect(denyMutate).toHaveBeenCalledWith("e1"));
  });

  it("drops an approved request once the refetched list no longer includes it", async () => {
    const { rerender } = renderList();
    expect(screen.getByText("Jamie Park")).toBeTruthy();
    // Simulate the post-approve invalidation returning the shorter list.
    mockUseJoinRequests.mockReturnValue({
      data: [makeRequest({ enrollment_id: "e2", full_name: "Chase Li", email: "chase@connect.ust.hk" })],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useJoinRequests>);
    rerender(
      <NextIntlClientProvider locale="en" messages={messages}>
        <JoinRequestApproval courseId="c1" />
      </NextIntlClientProvider>
    );
    expect(screen.queryByText("Jamie Park")).toBeNull();
    expect(screen.getByText("Chase Li")).toBeTruthy();
  });

  it("shows a soft notice (not an error) when the request was already decided (409)", async () => {
    approveMutate.mockRejectedValueOnce(
      new ApiError(409, "conflict", undefined, "NOT_PENDING")
    );
    renderList();
    fireEvent.click(screen.getAllByRole("button", { name: /Approve/i })[0]);
    await waitFor(() =>
      expect(screen.getByText(/already handled elsewhere/i)).toBeTruthy()
    );
    // It is a benign status banner, not an alert-role error.
    expect(screen.queryByText(/couldn't update this request/i)).toBeNull();
  });

  it("shows an error message on a generic failure", async () => {
    denyMutate.mockRejectedValueOnce(new ApiError(500, "boom"));
    renderList();
    fireEvent.click(screen.getAllByRole("button", { name: /Deny/i })[0]);
    await waitFor(() =>
      expect(screen.getByText(/couldn't update this request/i)).toBeTruthy()
    );
  });

  it("renders the empty state when nothing is pending", () => {
    mockUseJoinRequests.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useJoinRequests>);
    renderList();
    expect(screen.getByText(/No pending requests/i)).toBeTruthy();
  });
});
