"use client";

import { Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, Loader2, Unlink } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CanvasConnectButton } from "@/components/canvas/connect-button";
import {
  useCanvasConnection,
  useDisconnectCanvas,
} from "@/hooks/use-canvas";

export default function CanvasSettingsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <CanvasSettingsContent />
    </Suspense>
  );
}

function PageSkeleton() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-40 w-full rounded-[var(--radius-lg)]" />
    </div>
  );
}

function CanvasSettingsContent() {
  const searchParams = useSearchParams();
  const { data: connection, isLoading } = useCanvasConnection();
  const disconnect = useDisconnectCanvas();

  const justConnected = searchParams.get("connected") === "1";
  const error = searchParams.get("error");

  const handleDisconnect = useCallback(async () => {
    const confirmed = window.confirm(
      "Disconnect Canvas? Meli will stop syncing your Canvas courses."
    );
    if (!confirmed) return;
    await disconnect.mutateAsync();
  }, [disconnect]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--color-text)]">
          Canvas integration
        </h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          Connect your HKUST Canvas account so Meli can list courses, import
          materials, and sync rosters on your behalf.
        </p>
      </div>

      {justConnected && (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-success)] bg-[var(--color-success-light)] px-3 py-2 text-sm text-[var(--color-success)]">
          <CheckCircle2 className="size-4" />
          Canvas connected successfully.
        </div>
      )}

      {error && (
        <div className="rounded-[var(--radius-md)] border border-[var(--color-error)] bg-[var(--color-error-light)] px-3 py-2 text-sm text-[var(--color-error)]">
          Canvas connection failed: {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Connection status</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
              <Loader2 className="size-4 animate-spin" />
              Checking connection…
            </div>
          ) : connection?.connected ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-[var(--color-success)]">
                <CheckCircle2 className="size-4" />
                Connected
                {connection.status ? (
                  <span className="text-[var(--color-text-muted)]">
                    ({connection.status})
                  </span>
                ) : null}
              </div>
              <dl className="grid gap-2 text-sm">
                {connection.canvas_base_url ? (
                  <div className="flex gap-2">
                    <dt className="w-32 text-[var(--color-text-muted)]">
                      Canvas site
                    </dt>
                    <dd className="text-[var(--color-text)]">
                      {connection.canvas_base_url}
                    </dd>
                  </div>
                ) : null}
                {connection.canvas_user_id ? (
                  <div className="flex gap-2">
                    <dt className="w-32 text-[var(--color-text-muted)]">
                      Canvas user ID
                    </dt>
                    <dd className="font-mono text-[var(--color-text)]">
                      {connection.canvas_user_id}
                    </dd>
                  </div>
                ) : null}
              </dl>
              <Button
                variant="destructive"
                onClick={handleDisconnect}
                disabled={disconnect.isPending}
              >
                {disconnect.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Unlink className="size-4" />
                )}
                {disconnect.isPending ? "Disconnecting…" : "Disconnect Canvas"}
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-[var(--color-text-muted)]">
                You haven&apos;t connected Canvas yet. Connecting lets Meli read
                your course list, download files you select, and keep rosters
                in sync.
              </p>
              <CanvasConnectButton />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
