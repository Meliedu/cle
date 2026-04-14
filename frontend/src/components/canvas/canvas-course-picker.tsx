"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, ExternalLink, Link2, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CanvasConnectButton } from "@/components/canvas/connect-button";
import {
  useCanvasConnection,
  useCanvasCourses,
  useLinkCanvasCourse,
} from "@/hooks/use-canvas";
import type { CanvasCourseListing } from "@/lib/canvas-api";

export function CanvasCoursePicker() {
  const router = useRouter();
  const { data: connection, isLoading: connLoading } = useCanvasConnection();
  const connected = connection?.connected === true;
  const { data: courses, isLoading: coursesLoading } = useCanvasCourses(
    "teacher",
    connected
  );
  const link = useLinkCanvasCourse();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleLink = useCallback(
    async (canvasCourseId: number) => {
      setError(null);
      setPendingId(canvasCourseId);
      try {
        const { meli_course_id } = await link.mutateAsync(canvasCourseId);
        router.push(`/dashboard/courses/${meli_course_id}?tab=overview`);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Failed to link course";
        setError(message);
      } finally {
        setPendingId(null);
      }
    },
    [link, router]
  );

  if (connLoading) {
    return (
      <Card>
        <CardContent>
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!connected) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Link2 className="size-4" />
            Import from Canvas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-[var(--color-text-muted)]">
            Connect your Canvas account to import a course you already teach.
          </p>
          <CanvasConnectButton />
        </CardContent>
      </Card>
    );
  }

  const list: readonly CanvasCourseListing[] = courses ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="size-4" />
          Import from Canvas
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-[var(--color-text-muted)]">
          Pick a Canvas course you teach. Meli will create a linked course you
          can populate with materials and students.
        </p>

        {error && (
          <p className="text-sm text-[var(--color-error)]">{error}</p>
        )}

        {coursesLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : list.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            No Canvas courses where you&apos;re a teacher were found.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {list.map((c) => {
              const linked = !!c.already_linked_meli_course_id;
              const isPending = pendingId === c.canvas_course_id;
              return (
                <li
                  key={c.canvas_course_id}
                  className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium text-[var(--color-text)]">
                        {c.name}
                      </p>
                      {c.course_code && (
                        <Badge variant="secondary">{c.course_code}</Badge>
                      )}
                    </div>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {c.term ?? ""}
                    </p>
                  </div>
                  {linked ? (
                    <Button
                      variant="outline"
                      onClick={() =>
                        router.push(
                          `/dashboard/courses/${c.already_linked_meli_course_id}?tab=overview`
                        )
                      }
                    >
                      <CheckCircle2 className="size-4" />
                      Open in Meli
                      <ExternalLink className="size-3" />
                    </Button>
                  ) : (
                    <Button
                      onClick={() => handleLink(c.canvas_course_id)}
                      disabled={link.isPending}
                    >
                      {isPending ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Link2 className="size-4" />
                      )}
                      {isPending ? "Linking…" : "Link"}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
