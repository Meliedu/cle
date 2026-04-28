"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { useAssignments } from "@/hooks/use-assignments";
import { AssignmentForm } from "./assignment-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, X } from "lucide-react";
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

export function AssignmentList({ courseId }: Props) {
  const { data: assignments, isLoading } = useAssignments(courseId);
  const [showAdd, setShowAdd] = useState(false);

  const handleClose = useCallback(() => setShowAdd(false), []);

  const sorted = [...(assignments ?? [])].sort(
    (a, b) => new Date(a.due_at).getTime() - new Date(b.due_at).getTime()
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text)]">
          Assignments ({isLoading ? "..." : sorted.length})
        </h2>
        {!showAdd && (
          <Button size="sm" onClick={() => setShowAdd(true)}>
            <Plus className="size-4" />
            Add assignment
          </Button>
        )}
      </div>

      {showAdd && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">New Assignment</CardTitle>
              <Button size="sm" variant="ghost" onClick={handleClose}>
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <AssignmentForm courseId={courseId} onClose={handleClose} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded-[var(--radius-md)]" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No assignments yet.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {sorted.map((asgn) => (
                <li
                  key={asgn.id}
                  className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        href={`/dashboard/courses/${courseId}/assignments/${asgn.id}`}
                        className="text-sm font-medium text-[var(--color-primary)] hover:underline"
                      >
                        {asgn.title}
                      </Link>
                      {kindBadge(asgn.kind)}
                      <span
                        className={`inline-block rounded px-2 py-0.5 text-xs ${
                          asgn.is_published
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-stone-100 text-stone-600"
                        }`}
                      >
                        {asgn.is_published ? "Published" : "Draft"}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                      Due: {new Date(asgn.due_at).toLocaleString()}
                      {asgn.weight
                        ? ` · Weight: ${asgn.weight}`
                        : ""}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
