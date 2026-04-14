"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Info, Loader2, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CanvasConnectButton } from "@/components/canvas/connect-button";
import {
  useCanvasConnection,
  useCanvasCourses,
  useJoinCanvasCourse,
} from "@/hooks/use-canvas";
import type { CanvasCourseListing } from "@/lib/canvas-api";

interface StudentCanvasCoursesProps {
  readonly onJoined?: () => void;
}

export function StudentCanvasCourses({ onJoined }: StudentCanvasCoursesProps) {
  const router = useRouter();
  const { data: connection, isLoading: connLoading } = useCanvasConnection();
  const connected = connection?.connected === true;
  const { data: courses, isLoading: coursesLoading } = useCanvasCourses(
    "student",
    connected
  );
  const join = useJoinCanvasCourse();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleJoin = useCallback(
    async (canvasCourseId: number) => {
      setError(null);
      setPendingId(canvasCourseId);
      try {
        const { meli_course_id } = await join.mutateAsync(canvasCourseId);
        if (onJoined) onJoined();
        router.push(`/dashboard/courses/${meli_course_id}?tab=overview`);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to join course");
      } finally {
        setPendingId(null);
      }
    },
    [join, onJoined, router]
  );

  if (connLoading) {
    return <Skeleton className="h-24 w-full" />;
  }

  if (!connected) {
    return (
      <div className="space-y-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
        <p className="text-sm text-[var(--color-text-muted)]">
          Connect Canvas to see courses you&apos;re enrolled in and join them
          in one click.
        </p>
        <CanvasConnectButton />
      </div>
    );
  }

  const list: readonly CanvasCourseListing[] = courses ?? [];

  if (coursesLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }

  if (list.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No Canvas student enrollments found.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {error && <p className="text-sm text-[var(--color-error)]">{error}</p>}
      <ul className="divide-y divide-[var(--color-border)] rounded-[var(--radius-md)] border border-[var(--color-border)]">
        {list.map((c) => {
          const linked = !!c.already_linked_meli_course_id;
          const isPending = pendingId === c.canvas_course_id;
          return (
            <li
              key={c.canvas_course_id}
              className="flex items-center gap-3 px-3 py-2"
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
                  onClick={() => handleJoin(c.canvas_course_id)}
                  disabled={join.isPending}
                >
                  {isPending ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <LogIn className="size-4" />
                  )}
                  {isPending ? "Joining…" : "Join"}
                </Button>
              ) : (
                <div className="flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
                  <Info className="size-3.5" />
                  Instructor hasn&apos;t enabled Meli
                </div>
              )}
              {linked && (
                <span className="sr-only">
                  <CheckCircle2 className="size-4" />
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
