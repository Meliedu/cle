// frontend/src/components/decision/engine-mode-selector.tsx
"use client";
import {
  useEngineSettings,
  useUpdateEngineMode,
} from "@/hooks/use-engine-settings";
import type { EngineMode } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

const OPTIONS: { value: EngineMode; label: string; help: string }[] = [
  {
    value: "on",
    label: "On",
    help: "All enrolled students see personalised next-actions.",
  },
  {
    value: "off",
    label: "Off",
    help: "No next-actions are shown. Outcome telemetry is still recorded for the off arm.",
  },
  {
    value: "random_50",
    label: "Random 50/50",
    help:
      "Half of your students see next-actions, half don't. Each student is " +
      "deterministically placed by hash so they stay in the same arm session-to-session — clean A/B telemetry.",
  },
];

export function EngineModeSelector({ courseId }: Props) {
  const { data, isLoading } = useEngineSettings(courseId);
  const update = useUpdateEngineMode(courseId);
  if (isLoading || !data) return null;
  return (
    <fieldset className="space-y-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <legend className="text-sm font-medium text-[var(--color-text)]">
        Adaptive engine mode
      </legend>
      <p className="text-xs text-[var(--color-muted)]">
        Currently {data.overrides_count} per-student override
        {data.overrides_count === 1 ? "" : "s"} active.
      </p>
      {OPTIONS.map((o) => (
        <label
          key={o.value}
          className="flex items-start gap-2 text-sm text-[var(--color-text)]"
        >
          <input
            type="radio"
            checked={data.mode === o.value}
            disabled={update.isPending}
            onChange={() => update.mutate(o.value)}
            className="mt-1"
          />
          <span>
            <strong>{o.label}</strong>
            <br />
            <span className="text-xs text-[var(--color-muted)]">{o.help}</span>
          </span>
        </label>
      ))}
    </fieldset>
  );
}
