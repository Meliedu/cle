"use client";

import Link from "next/link";
import { useAssignments } from "@/hooks/use-assignments";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AssignmentKind } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
}

function kindBadge(kind: AssignmentKind) {
  return (
    <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-primary-light)] text-[var(--color-primary)]">
      {kind.replace("_", " ")}
    </span>
  );
}

export function StudentAssignmentList({ courseId }: Props) {
  const { data: assignments = [], isLoading } = useAssignments(courseId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-[var(--radius-md)]" />
        ))}
      </div>
    );
  }

  // Backend already filters is_published for students
  if (assignments.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No assignments yet.
      </p>
    );
  }

  const sorted = [...assignments].sort(
    (a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
  );

  return (
    <Card>
      <CardContent className="pt-4">
        <ul className="divide-y divide-[var(--color-border)]">
          {sorted.map((a) => (
            <li key={a.id} className="py-3 first:pt-0 last:pb-0">
              {/* TODO(phase-2): show user's own submission status badge once backend exposes per-user submission lookup */}
              <Link
                href={`/dashboard/courses/${courseId}/assignments/${a.id}/submit`}
                className="block group"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-[var(--color-primary)] group-hover:underline">
                    {a.title}
                  </span>
                  {kindBadge(a.kind)}
                </div>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  Due: {new Date(a.due_at).toLocaleString()}
                  {a.weight ? ` · Weight: ${a.weight}` : ""}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
