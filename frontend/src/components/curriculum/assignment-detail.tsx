"use client";

import { useState, useCallback } from "react";
import { useAssignments } from "@/hooks/use-assignments";
import { useSubmissions, useGradeSubmission } from "@/hooks/use-assignment-submissions";
import { AssignmentForm } from "./assignment-form";
import { SubmissionStatusBadge } from "./submission-status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Pencil, X, Loader2 } from "lucide-react";
import type { AssignmentSubmission } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
  readonly assignmentId: string;
}

interface GradeFormState {
  readonly score: string;
  readonly feedback: string;
  readonly status: "graded" | "excused";
}

const INITIAL_GRADE_FORM: GradeFormState = {
  score: "",
  feedback: "",
  status: "graded",
};

function GradeSubmissionForm({
  courseId,
  assignmentId,
  submission,
  onClose,
}: {
  courseId: string;
  assignmentId: string;
  submission: AssignmentSubmission;
  onClose: () => void;
}) {
  const gradeSubmission = useGradeSubmission(courseId, assignmentId);
  const [form, setForm] = useState<GradeFormState>({
    ...INITIAL_GRADE_FORM,
    score: submission.score ?? "",
    status: "graded",
  });
  const [error, setError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof GradeFormState>(field: K, value: GradeFormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setError(null);
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!form.score.trim()) {
        setError("Score is required");
        return;
      }
      setError(null);
      try {
        await gradeSubmission.mutateAsync({
          submissionId: submission.id,
          score: form.score.trim(),
          feedback: form.feedback.trim() || undefined,
          status: form.status,
        });
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to grade submission");
      }
    },
    [form, submission.id, gradeSubmission, onClose]
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-3 border-t border-[var(--color-border)] pt-3 mt-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor={`score-${submission.id}`}>Score</Label>
          <Input
            id={`score-${submission.id}`}
            placeholder="e.g. 85"
            value={form.score}
            onChange={(e) => updateField("score", e.target.value)}
            autoFocus
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor={`status-${submission.id}`}>Status</Label>
          <select
            id={`status-${submission.id}`}
            value={form.status}
            onChange={(e) =>
              updateField("status", e.target.value as "graded" | "excused")
            }
            className="h-9 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-background px-3 text-sm"
          >
            <option value="graded">graded</option>
            <option value="excused">excused</option>
          </select>
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor={`feedback-${submission.id}`}>Feedback (optional)</Label>
        <Textarea
          id={`feedback-${submission.id}`}
          rows={2}
          placeholder="Optional feedback for the student"
          value={form.feedback}
          onChange={(e) => updateField("feedback", e.target.value)}
        />
      </div>
      {error && (
        <p className="text-xs text-[var(--color-error)]">{error}</p>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={gradeSubmission.isPending}>
          {gradeSubmission.isPending && (
            <Loader2 className="size-3 animate-spin" />
          )}
          Save grade
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onClose}
          disabled={gradeSubmission.isPending}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}

function SubmissionRow({
  submission,
  courseId,
  assignmentId,
}: {
  submission: AssignmentSubmission;
  courseId: string;
  assignmentId: string;
}) {
  const [grading, setGrading] = useState(false);
  const needsGrading =
    submission.status === "submitted" || submission.status === "late";

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[var(--color-text)] truncate">
            {submission.user_id}
          </p>
          {submission.score && (
            <p className="text-xs text-[var(--color-text-muted)]">
              Score: {submission.score}
            </p>
          )}
        </div>
        <SubmissionStatusBadge status={submission.status} />
        {needsGrading && !grading && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setGrading(true)}
          >
            <Pencil className="size-3" />
            Grade
          </Button>
        )}
        {grading && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setGrading(false)}
          >
            <X className="size-3" />
          </Button>
        )}
      </div>
      {grading && (
        <GradeSubmissionForm
          courseId={courseId}
          assignmentId={assignmentId}
          submission={submission}
          onClose={() => setGrading(false)}
        />
      )}
    </li>
  );
}

export function AssignmentDetail({ courseId, assignmentId }: Props) {
  const { data: assignments, isLoading: assignmentsLoading } =
    useAssignments(courseId);
  const { data: submissions, isLoading: submissionsLoading } = useSubmissions(
    courseId,
    assignmentId
  );
  const [editing, setEditing] = useState(false);

  const assignment = (assignments ?? []).find((a) => a.id === assignmentId);

  if (assignmentsLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (!assignment) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Assignment not found.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Assignment details / edit */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>{assignment.title}</CardTitle>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing((v) => !v)}
            >
              {editing ? (
                <>
                  <X className="size-4" /> Cancel
                </>
              ) : (
                <>
                  <Pencil className="size-4" /> Edit
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {editing ? (
            <AssignmentForm
              courseId={courseId}
              assignment={assignment}
              onClose={() => setEditing(false)}
            />
          ) : (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div>
                <dt className="text-[var(--color-text-muted)]">Kind</dt>
                <dd className="font-medium capitalize">
                  {assignment.kind.replace("_", " ")}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--color-text-muted)]">Due</dt>
                <dd className="font-medium">
                  {new Date(assignment.due_at).toLocaleString()}
                </dd>
              </div>
              {assignment.weight && (
                <div>
                  <dt className="text-[var(--color-text-muted)]">Weight</dt>
                  <dd className="font-medium">{assignment.weight}</dd>
                </div>
              )}
              <div>
                <dt className="text-[var(--color-text-muted)]">Status</dt>
                <dd>
                  <span
                    className={`inline-block rounded px-2 py-0.5 text-xs ${
                      assignment.is_published
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-stone-100 text-stone-600"
                    }`}
                  >
                    {assignment.is_published ? "Published" : "Draft"}
                  </span>
                </dd>
              </div>
              {assignment.description && (
                <div className="col-span-2">
                  <dt className="text-[var(--color-text-muted)]">Description</dt>
                  <dd className="mt-1 leading-relaxed text-[var(--color-text-secondary)]">
                    {assignment.description}
                  </dd>
                </div>
              )}
            </dl>
          )}
        </CardContent>
      </Card>

      {/* Submissions roster */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Submissions (
            {submissionsLoading ? "..." : (submissions ?? []).length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {submissionsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 rounded-[var(--radius-md)]" />
              ))}
            </div>
          ) : !submissions || submissions.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No submissions yet.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {submissions.map((sub) => (
                <SubmissionRow
                  key={sub.id}
                  submission={sub}
                  courseId={courseId}
                  assignmentId={assignmentId}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
