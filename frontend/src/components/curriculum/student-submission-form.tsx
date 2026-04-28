"use client";

import { useState } from "react";
import { useUpsertMySubmission } from "@/hooks/use-assignment-submissions";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Props {
  readonly courseId: string;
  readonly assignmentId: string;
}

export function StudentSubmissionForm({ courseId, assignmentId }: Props) {
  const [text, setText] = useState("");
  const upsert = useUpsertMySubmission(courseId, assignmentId);

  const onSaveDraft = () =>
    upsert.mutate({ status: "in_progress", submission_payload: { text } });

  const onSubmit = () =>
    upsert.mutate({ status: "submitted", submission_payload: { text } });

  return (
    <div className="space-y-4">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        placeholder="Write your submission..."
        className="min-h-[200px] w-full"
      />
      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={onSaveDraft}
          disabled={upsert.isPending || text.trim().length === 0}
        >
          Save draft
        </Button>
        <Button
          onClick={onSubmit}
          disabled={upsert.isPending || text.trim().length === 0}
        >
          Submit
        </Button>
      </div>
      {upsert.isSuccess && (
        <p className="text-sm text-[var(--color-success)]">Saved.</p>
      )}
      {upsert.isError && (
        <p className="text-sm text-[var(--color-error)]">
          {upsert.error instanceof Error
            ? upsert.error.message
            : "Save failed."}
        </p>
      )}
    </div>
  );
}
