import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoleLoadError } from "@/components/layout/role-load-error";
import { useAuth } from "@/hooks/use-auth";

const signOut = vi.fn(async () => {});

vi.mock("@/hooks/use-auth", () => ({
  useAuth: vi.fn(),
}));

const mockUseAuth = vi.mocked(useAuth);

function renderWithClient(node: ReactNode) {
  const queryClient = new QueryClient();
  const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
  const utils = render(
    <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>
  );
  return { ...utils, invalidateSpy };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("RoleLoadError", () => {
  it("renders the failure copy plus retry and sign-out affordances", () => {
    mockUseAuth.mockReturnValue({
      getToken: vi.fn(),
      isSignedIn: true,
      isLoaded: true,
      userId: "u1",
      signOut,
    });

    renderWithClient(<RoleLoadError />);

    expect(screen.getByText("We couldn't load your account")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeTruthy();
  });

  it("invalidates the me query on retry and signs out on sign-out", () => {
    mockUseAuth.mockReturnValue({
      getToken: vi.fn(),
      isSignedIn: true,
      isLoaded: true,
      userId: "u1",
      signOut,
    });

    const { invalidateSpy } = renderWithClient(<RoleLoadError />);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["auth", "me"] });

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledWith({ redirectUrl: "/sign-in" });
  });
});
