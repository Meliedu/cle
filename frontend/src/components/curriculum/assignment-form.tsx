"use client";

import { useState, useCallback } from "react";
import {
  useCreateAssignment,
  useUpdateAssignment,
} from "@/hooks/use-assignments";
import { useModules } from "@/hooks/use-modules";
import { useMeetings } from "@/hooks/use-meetings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import type { Assignment, AssignmentKind } from "@/lib/curriculum-types";

const ASSIGNMENT_KINDS: readonly AssignmentKind[] = [
  "essay",
  "project",
  "quiz",
  "reading",
  "presentation",
  "lab",
  "problem_set",
  "participation",
  "other",
];

interface Props {
  readonly courseId: string;
  readonly assignment?: Assignment;
  readonly onClose?: () => void;
}

interface FormState {
  readonly title: string;
  readonly kind: AssignmentKind | "";
  readonly due_at: string;
  readonly weight: string;
  readonly description: string;
  readonly module_id: string;
  readonly meeting_id: string;
  readonly is_published: boolean;
}

function toDatetimeLocal(iso: string): string {
  return iso.slice(0, 16);
}

function buildInitialForm(assignment?: Assignment): FormState {
  if (assignment) {
    return {
      title: assignment.title,
      kind: assignment.kind,
      due_at: toDatetimeLocal(assignment.due_at),
      weight: assignment.weight ?? "",
      description: assignment.description ?? "",
      module_id: assignment.module_id ?? "__none__",
      meeting_id: assignment.meeting_id ?? "__none__",
      is_published: assignment.is_published,
    };
  }
  return {
    title: "",
    kind: "",
    due_at: "",
    weight: "",
    description: "",
    module_id: "__none__",
    meeting_id: "__none__",
    is_published: false,
  };
}

export function AssignmentForm({ courseId, assignment, onClose }: Props) {
  const { data: modules } = useModules(courseId);
  const { data: meetings } = useMeetings(courseId);
  const createAssignment = useCreateAssignment(courseId);
  const updateAssignment = useUpdateAssignment(courseId);

  const [form, setForm] = useState<FormState>(() => buildInitialForm(assignment));
  const [error, setError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setError(null);
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!form.title.trim()) {
        setError("Title is required");
        return;
      }
      if (!form.kind) {
        setError("Assignment kind is required");
        return;
      }
      if (!form.due_at) {
        setError("Due date is required");
        return;
      }
      setError(null);

      const payload = {
        title: form.title.trim(),
        kind: form.kind as AssignmentKind,
        due_at: new Date(form.due_at).toISOString(),
        description: form.description.trim() || undefined,
        weight: form.weight.trim() || undefined,
        module_id: form.module_id !== "__none__" ? form.module_id : undefined,
        meeting_id: form.meeting_id !== "__none__" ? form.meeting_id : undefined,
        is_published: form.is_published,
      };

      try {
        if (assignment) {
          await updateAssignment.mutateAsync({
            assignmentId: assignment.id,
            patch: payload,
          });
        } else {
          await createAssignment.mutateAsync(payload);
        }
        onClose?.();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to save assignment"
        );
      }
    },
    [form, assignment, createAssignment, updateAssignment, onClose]
  );

  const isPending = createAssignment.isPending || updateAssignment.isPending;
  const sortedMeetings = [...(meetings ?? [])].sort(
    (a, b) =>
      new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="asgn-title">
          Title <span className="text-[var(--color-error)]">*</span>
        </Label>
        <Input
          id="asgn-title"
          placeholder="Assignment title"
          value={form.title}
          onChange={(e) => updateField("title", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>
            Kind <span className="text-[var(--color-error)]">*</span>
          </Label>
          <Select
            value={form.kind || "__none__"}
            onValueChange={(val) =>
              updateField("kind", val === "__none__" ? "" : (val as AssignmentKind))
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">Select type</SelectItem>
              {ASSIGNMENT_KINDS.map((k) => (
                <SelectItem key={k} value={k}>
                  {k.replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="asgn-weight">Weight (optional)</Label>
          <Input
            id="asgn-weight"
            type="number"
            step="0.01"
            min={0}
            placeholder="e.g. 0.20"
            value={form.weight}
            onChange={(e) => updateField("weight", e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="asgn-due">
          Due at <span className="text-[var(--color-error)]">*</span>
        </Label>
        <Input
          id="asgn-due"
          type="datetime-local"
          value={form.due_at}
          onChange={(e) => updateField("due_at", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="asgn-desc">Description</Label>
        <Textarea
          id="asgn-desc"
          placeholder="Optional instructions or description"
          rows={3}
          value={form.description}
          onChange={(e) => updateField("description", e.target.value)}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Module</Label>
          <Select
            value={form.module_id}
            onValueChange={(val) => updateField("module_id", val ?? "__none__")}
          >
            <SelectTrigger>
              <SelectValue placeholder="(none)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(none)</SelectItem>
              {(modules ?? []).map((mod) => (
                <SelectItem key={mod.id} value={mod.id}>
                  {mod.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>Meeting</Label>
          <Select
            value={form.meeting_id}
            onValueChange={(val) => updateField("meeting_id", val ?? "__none__")}
          >
            <SelectTrigger>
              <SelectValue placeholder="(none)" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">(none)</SelectItem>
              {sortedMeetings.map((mtg) => (
                <SelectItem key={mtg.id} value={mtg.id}>
                  #{mtg.meeting_index}{" "}
                  {mtg.title ?? new Date(mtg.scheduled_at).toLocaleDateString()}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          id="asgn-published"
          type="checkbox"
          checked={form.is_published}
          onChange={(e) => updateField("is_published", e.target.checked)}
          className="size-4 rounded border-[var(--color-border)]"
        />
        <Label htmlFor="asgn-published" className="cursor-pointer">
          Published (visible to students)
        </Label>
      </div>

      {error && (
        <p className="text-sm text-[var(--color-error)]">{error}</p>
      )}

      <div className="flex justify-end gap-2">
        {onClose && (
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isPending}>
          {isPending && <Loader2 className="size-4 animate-spin" />}
          {assignment ? "Save changes" : "Create assignment"}
        </Button>
      </div>
    </form>
  );
}
