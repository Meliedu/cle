"use client";

import { useState, useCallback } from "react";
import {
  useObjectives,
  useDeleteObjective,
} from "@/hooks/use-objectives";
import { ObjectiveForm } from "./objective-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Pencil, Trash2, Plus, X } from "lucide-react";
import type { LearningObjective } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
}

export function ObjectivesEditor({ courseId }: Props) {
  const { data: objectives, isLoading } = useObjectives(courseId);
  const deleteObjective = useDeleteObjective(courseId);

  const [showAdd, setShowAdd] = useState(false);
  const [editingObjective, setEditingObjective] =
    useState<LearningObjective | null>(null);

  const handleDelete = useCallback(
    async (obj: LearningObjective) => {
      const preview = obj.statement.slice(0, 60);
      if (!window.confirm(`Delete objective: "${preview}..."?`)) return;
      try {
        await deleteObjective.mutateAsync(obj.id);
      } catch {
        // silent
      }
    },
    [deleteObjective]
  );

  const sorted = [...(objectives ?? [])].sort(
    (a, b) => a.order_index - b.order_index
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--color-text-muted)]">
          {isLoading ? "Loading..." : `${sorted.length} objective(s)`}
        </p>
        {!showAdd && (
          <Button
            size="sm"
            onClick={() => {
              setEditingObjective(null);
              setShowAdd(true);
            }}
          >
            <Plus className="size-4" />
            Add objective
          </Button>
        )}
      </div>

      {/* Add panel */}
      {showAdd && !editingObjective && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">New Objective</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <ObjectiveForm
              courseId={courseId}
              onClose={() => setShowAdd(false)}
            />
          </CardContent>
        </Card>
      )}

      {/* Edit panel */}
      {editingObjective && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Edit Objective</CardTitle>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setEditingObjective(null)}
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <ObjectiveForm
              courseId={courseId}
              objective={editingObjective}
              onClose={() => setEditingObjective(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* List */}
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
              No objectives yet.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {sorted.map((obj) => (
                <li
                  key={obj.id}
                  className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-[var(--color-text)]">
                      {obj.statement}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {obj.bloom_level && (
                        <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                          {obj.bloom_level}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setShowAdd(false);
                        setEditingObjective(obj);
                      }}
                      aria-label={`Edit objective: ${obj.statement.slice(0, 40)}`}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(obj)}
                      disabled={deleteObjective.isPending}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-error)]"
                      aria-label={`Delete objective: ${obj.statement.slice(0, 40)}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
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
