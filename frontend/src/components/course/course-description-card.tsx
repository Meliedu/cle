"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useUpdateCourse } from "@/hooks/use-courses";

interface CourseDescriptionCardProps {
  readonly courseId: string;
  readonly description: string | null;
  readonly canEdit: boolean;
}

const DESCRIPTION_MAX_LENGTH = 2000;

export function CourseDescriptionCard({
  courseId,
  description,
  canEdit,
}: CourseDescriptionCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(description ?? "");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const updateCourse = useUpdateCourse(courseId);

  useEffect(() => {
    if (!isEditing) {
      setDraft(description ?? "");
    }
  }, [description, isEditing]);

  const startEdit = useCallback(() => {
    setDraft(description ?? "");
    setSubmitError(null);
    setIsEditing(true);
  }, [description]);

  const cancelEdit = useCallback(() => {
    setIsEditing(false);
    setSubmitError(null);
    setDraft(description ?? "");
  }, [description]);

  const save = useCallback(async () => {
    const trimmed = draft.trim();
    const next = trimmed.length === 0 ? null : trimmed;
    if (next === (description ?? null)) {
      setIsEditing(false);
      return;
    }
    setSubmitError(null);
    try {
      await updateCourse.mutateAsync({ description: next });
      setIsEditing(false);
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "Failed to save description";
      setSubmitError(message);
    }
  }, [draft, description, updateCourse]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
        <CardTitle>About this course</CardTitle>
        {canEdit && !isEditing && (
          <Button
            variant="ghost"
            size="sm"
            onClick={startEdit}
            aria-label="Edit course description"
          >
            <Pencil className="size-4" />
            Edit
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {isEditing ? (
          <div className="space-y-3">
            <Textarea
              id="course-description-edit"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={5}
              maxLength={DESCRIPTION_MAX_LENGTH}
              placeholder="Describe what students will learn in this course..."
              aria-label="Course description"
              disabled={updateCourse.isPending}
            />
            <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
              <span>
                {draft.length}/{DESCRIPTION_MAX_LENGTH}
              </span>
            </div>
            {submitError && (
              <p className="text-sm text-[var(--color-error)]">{submitError}</p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={cancelEdit}
                disabled={updateCourse.isPending}
              >
                <X className="size-4" />
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={save}
                disabled={updateCourse.isPending}
              >
                {updateCourse.isPending && (
                  <Loader2 className="size-4 animate-spin" />
                )}
                {updateCourse.isPending ? "Saving..." : "Save"}
              </Button>
            </div>
          </div>
        ) : (
          <p className="leading-relaxed whitespace-pre-wrap text-[var(--color-text-secondary)]">
            {description ?? "No description provided."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
