"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function DashboardError({
  error,
  reset,
}: {
  readonly error: Error & { digest?: string };
  readonly reset: () => void;
}) {
  useEffect(() => {
    // Surface the digest so server-side logs can be correlated; avoid
    // logging the raw message which may contain user-facing PII.
    console.error("[dashboard error]", error.digest ?? error.name);
  }, [error]);

  return (
    <div className="mx-auto flex max-w-lg flex-col items-start gap-4 py-16">
      <h2 className="text-2xl font-semibold text-[var(--color-text)]">
        Something went wrong
      </h2>
      <p className="text-sm text-[var(--color-text-muted)]">
        We hit an unexpected error loading this view. You can retry, or head
        back to the dashboard home.
      </p>
      <div className="flex gap-2">
        <Button onClick={reset}>Try again</Button>
      </div>
    </div>
  );
}
