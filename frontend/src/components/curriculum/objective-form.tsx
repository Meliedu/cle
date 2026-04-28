"use client";

import { useState, useCallback } from "react";
import {
  useCreateObjective,
  useUpdateObjective,
} from "@/hooks/use-objectives";
import { useModules } from "@/hooks/use-modules";
import { useMeetings } from "@/hooks/use-meetings";
import { Button } from "@/components/ui/button";
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
import type { BloomLevel, LearningObjective } from "@/lib/curriculum-types";

const BLOOM_LEVELS: readonly BloomLevel[] = [
  "remember",
  "understand",
  "apply",
  "analyze",
  "evaluate",
  "create",
];

interface Props {
  readonly courseId: string;
  readonly objective?: LearningObjective;
  readonly onClose?: () => void;
}

interface FormState {
  readonly statement: string;
  readonly bloom_level: BloomLevel | "";
  readonly module_id: string;
  readonly meeting_id: string;
}

function buildInitialForm(objective?: LearningObjective): FormState {
  if (objective) {
    return {
      statement: objective.statement,
      bloom_level: objective.bloom_level ?? "",
      module_id: objective.module_id ?? "__none__",
      meeting_id: objective.meeting_id ?? "__none__",
    };
  }
  return {
    statement: "",
    bloom_level: "",
    module_id: "__none__",
    meeting_id: "__none__",
  };
}

export function ObjectiveForm({ courseId, objective, onClose }: Props) {
  const { data: modules } = useModules(courseId);
  const { data: meetings } = useMeetings(courseId);
  const createObjective = useCreateObjective(courseId);
  const updateObjective = useUpdateObjective(courseId);

  const [form, setForm] = useState<FormState>(() => buildInitialForm(objective));
  const [error, setError] = useState<string | null>(null);

  const updateField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setError(null);
    },
    []
  );

  const hasBothLinked =
    form.module_id !== "__none__" && form.meeting_id !== "__none__";

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      if (!form.statement.trim()) {
        setError("Statement is required");
        return;
      }
      if (hasBothLinked) {
        setError("Cannot link to both a module and a meeting simultaneously");
        return;
      }
      setError(null);

      const payload = {
        statement: form.statement.trim(),
        bloom_level: form.bloom_level || undefined,
        module_id: form.module_id !== "__none__" ? form.module_id : undefined,
        meeting_id: form.meeting_id !== "__none__" ? form.meeting_id : undefined,
      };

      try {
        if (objective) {
          await updateObjective.mutateAsync({
            objectiveId: objective.id,
            patch: payload,
          });
        } else {
          await createObjective.mutateAsync(payload);
        }
        onClose?.();
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to save objective"
        );
      }
    },
    [form, hasBothLinked, objective, createObjective, updateObjective, onClose]
  );

  const isPending = createObjective.isPending || updateObjective.isPending;
  const sortedMeetings = [...(meetings ?? [])].sort(
    (a, b) =>
      new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="obj-statement">
          Statement <span className="text-[var(--color-error)]">*</span>
        </Label>
        <Textarea
          id="obj-statement"
          placeholder="Students will be able to..."
          rows={3}
          value={form.statement}
          onChange={(e) => updateField("statement", e.target.value)}
        />
      </div>

      <div className="space-y-1.5">
        <Label>Bloom&apos;s Level</Label>
        <Select
          value={form.bloom_level || "__none__"}
          onValueChange={(val) =>
            updateField("bloom_level", val === "__none__" ? "" : (val as BloomLevel))
          }
        >
          <SelectTrigger>
            <SelectValue placeholder="(not set)" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">(not set)</SelectItem>
            {BLOOM_LEVELS.map((level) => (
              <SelectItem key={level} value={level}>
                {level.charAt(0).toUpperCase() + level.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
                  #{mtg.meeting_index} {mtg.title ?? new Date(mtg.scheduled_at).toLocaleDateString()}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {hasBothLinked && (
        <p className="text-xs text-[var(--color-error)]">
          Cannot link to both a module and a meeting. Clear one of them.
        </p>
      )}

      {error && !hasBothLinked && (
        <p className="text-sm text-[var(--color-error)]">{error}</p>
      )}

      <div className="flex justify-end gap-2">
        {onClose && (
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={isPending || hasBothLinked}>
          {isPending && <Loader2 className="size-4 animate-spin" />}
          {objective ? "Save changes" : "Add objective"}
        </Button>
      </div>
    </form>
  );
}
