"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StateBanner } from "@/components/patterns";
import { useEnrollByCode, joinErrorReason } from "@/hooks/use-enrollment";
import { StudentCanvasCourses } from "@/components/canvas/student-canvas-courses";
import { CANVAS_ENABLED } from "@/lib/features";

interface JoinCourseDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

function normalize(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/** Human copy for each typed join-error reason. */
const JOIN_ERROR_COPY: Record<
  ReturnType<typeof joinErrorReason>,
  string
> = {
  invalid: "No course matches that code",
  inactive: "This join code is no longer active. Ask your instructor for a current one.",
  not_open: "This course isn't open for joining yet. Try again once your instructor publishes it.",
  unknown: "Could not join course. Please try again.",
};

export function JoinCourseDialog({ open, onOpenChange }: JoinCourseDialogProps) {
  const router = useRouter();
  const enroll = useEnrollByCode();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Set once a `code_plus_approval` join lands `pending`: a pending student
  // cannot read the workspace, so we surface an awaiting-approval state here
  // instead of routing them into `/dashboard/courses/{id}`.
  const [pending, setPending] = useState(false);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      if (!next) {
        setCode("");
        setError(null);
        setPending(false);
      }
      onOpenChange(next);
    },
    [onOpenChange],
  );

  const handleSubmit = useCallback(
    async (event: { preventDefault: () => void }) => {
      event.preventDefault();
      const normalized = normalize(code);
      if (normalized.length !== 8) {
        setError("Enrollment codes are 8 characters");
        return;
      }

      setError(null);
      try {
        const result = await enroll.mutateAsync(normalized);
        // The endpoint returns `{ course, enrollment_status }` (P2 Task 5).
        // Branch on status: active → workspace; pending → awaiting approval
        // (never route a pending student into a course they can't read yet).
        if (result.enrollment_status === "active") {
          handleOpenChange(false);
          router.push(`/dashboard/courses/${result.course.id}?tab=overview`);
          return;
        }
        setPending(true);
      } catch (err: unknown) {
        setError(JOIN_ERROR_COPY[joinErrorReason(err)]);
      }
    },
    [code, enroll, handleOpenChange, router],
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Join a Course</DialogTitle>
          <DialogDescription>
            {pending
              ? "Your request was sent to the instructor."
              : "Enter the 8-character enrollment code your instructor shared."}
          </DialogDescription>
        </DialogHeader>

        {pending && (
          <div className="space-y-4">
            <StateBanner
              tone="waiting"
              title="Awaiting approval"
              reason="This course requires instructor approval. You'll get access once your request is approved."
            />
            <DialogFooter>
              <Button type="button" onClick={() => handleOpenChange(false)}>
                Done
              </Button>
            </DialogFooter>
          </div>
        )}

        {!pending && CANVAS_ENABLED && (
          <>
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-[var(--color-text)]">
                My Canvas courses
              </h3>
              <StudentCanvasCourses onJoined={() => handleOpenChange(false)} />
            </div>

            <div className="relative my-2 flex items-center gap-2">
              <div className="h-px flex-1 bg-[var(--color-border)]" />
              <span className="text-xs uppercase tracking-wider text-[var(--color-text-muted)]">
                or
              </span>
              <div className="h-px flex-1 bg-[var(--color-border)]" />
            </div>
          </>
        )}

        {!pending && (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="enroll-code">Enrollment code</Label>
            <Input
              id="enroll-code"
              autoFocus
              autoComplete="off"
              spellCheck={false}
              placeholder="ABCD2345"
              value={code}
              onChange={(e) => {
                setCode(normalize(e.target.value));
                if (error) setError(null);
              }}
              maxLength={12}
              className="font-mono uppercase tracking-[0.3em]"
              aria-invalid={!!error}
              aria-describedby={error ? "enroll-code-error" : undefined}
            />
            {error && (
              <p id="enroll-code-error" className="text-xs text-[var(--color-error)]">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={enroll.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={enroll.isPending}>
              {enroll.isPending && <Loader2 className="size-4 animate-spin" />}
              {enroll.isPending ? "Joining..." : "Join Course"}
            </Button>
          </DialogFooter>
        </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
