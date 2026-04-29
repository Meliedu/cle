"use client";

import { useState, useCallback } from "react";
import { useCreateMeeting, useUpdateMeeting } from "@/hooks/use-meetings";
import { useModules } from "@/hooks/use-modules";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import type { CourseMeeting } from "@/lib/curriculum-types";
import { ConceptTagList } from "@/components/concepts/concept-tag-pill";

interface Props {
  readonly courseId: string;
  readonly meeting?: CourseMeeting;
  readonly onClose?: () => void;
}

interface FormState {
  readonly meeting_index: string;
  readonly title: string;
  readonly scheduled_at: string;
  readonly duration_minutes: string;
  readonly location: string;
  readonly module_id: string;
}

function toDatetimeLocal(iso: string): string {
  // Convert ISO string to datetime-local format (YYYY-MM-DDTHH:mm)
  return iso.slice(0, 16);
}

function buildInitialForm(meeting?: CourseMeeting): FormState {
  if (meeting) {
    return {
      meeting_index: String(meeting.meeting_index),
      title: meeting.title ?? "",
      scheduled_at: toDatetimeLocal(meeting.scheduled_at),
      duration_minutes: String(meeting.duration_minutes),
      location: meeting.location ?? "",
      module_id: meeting.module_id ?? "__none__",
    };
  }
  return {
    meeting_index: "",
    title: "",
    scheduled_at: "",
    duration_minutes: "60",
    location: "",
    module_id: "__none__",
  };
}

export function MeetingForm({ courseId, meeting, onClose }: Props) {
  const { data: modules } = useModules(courseId);
  const createMeeting = useCreateMeeting(courseId);
  const updateMeeting = useUpdateMeeting(courseId);

  const [form, setForm] = useState<FormState>(() => buildInitialForm(meeting));
  const [error, setError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!form.scheduled_at) {
        setError("Scheduled date/time is required");
        return;
      }
      if (!form.meeting_index) {
        setError("Meeting index is required");
        return;
      }
      setError(null);

      const payload = {
        meeting_index: Number(form.meeting_index),
        title: form.title.trim() || undefined,
        scheduled_at: new Date(form.scheduled_at).toISOString(),
        duration_minutes: Number(form.duration_minutes) || 60,
        location: form.location.trim() || undefined,
        module_id: form.module_id !== "__none__" ? form.module_id : undefined,
      };

      try {
        if (meeting) {
          await updateMeeting.mutateAsync({
            meetingId: meeting.id,
            patch: payload,
          });
        } else {
          await createMeeting.mutateAsync(payload);
        }
        onClose?.();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to save meeting"
        );
      }
    },
    [form, meeting, createMeeting, updateMeeting, onClose]
  );

  const isPending = createMeeting.isPending || updateMeeting.isPending;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {meeting && (
        <ConceptTagList targetKind="meeting" targetId={meeting.id} />
      )}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="mtg-index">Meeting #</Label>
          <Input
            id="mtg-index"
            type="number"
            min={1}
            placeholder="1"
            value={form.meeting_index}
            onChange={(e) => updateField("meeting_index", e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="mtg-duration">Duration (min)</Label>
          <Input
            id="mtg-duration"
            type="number"
            min={1}
            value={form.duration_minutes}
            onChange={(e) => updateField("duration_minutes", e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="mtg-title">Title</Label>
        <Input
          id="mtg-title"
          placeholder="Optional title"
          value={form.title}
          onChange={(e) => updateField("title", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="mtg-scheduled">
          Scheduled at <span className="text-[var(--color-error)]">*</span>
        </Label>
        <Input
          id="mtg-scheduled"
          type="datetime-local"
          value={form.scheduled_at}
          onChange={(e) => updateField("scheduled_at", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="mtg-location">Location</Label>
        <Input
          id="mtg-location"
          placeholder="e.g. Room 2301"
          value={form.location}
          onChange={(e) => updateField("location", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Module</Label>
        <Select
          value={form.module_id}
          onValueChange={(val) => updateField("module_id", val ?? "__none__")}
        >
          <SelectTrigger>
            <SelectValue placeholder="(no module)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">(no module)</SelectItem>
            {(modules ?? []).map((mod) => (
              <SelectItem key={mod.id} value={mod.id}>
                {mod.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
          {meeting ? "Save changes" : "Add meeting"}
        </Button>
      </div>
    </form>
  );
}
