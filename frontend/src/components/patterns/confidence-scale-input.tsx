"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";
import type { ConfidenceScale } from "@/lib/pilot-config";

export interface ConfidenceScaleInputProps {
  /** The pilot's confidence scale — drives the ordered −2..+2 points + labels. */
  readonly scale: ConfidenceScale;
  /** The selected scale point, or `null` when nothing is chosen yet. */
  readonly value: number | null;
  readonly onChange: (value: number) => void;
  readonly disabled?: boolean;
  /**
   * Radio-group `name`. Radios sharing a name are mutually exclusive, so a page
   * rendering several scale inputs must give each a distinct name. Defaults to a
   * stable generated id so independent instances never collide by accident.
   */
  readonly name?: string;
}

const OPTION_BASE =
  "flex cursor-pointer items-center gap-2.5 rounded-[var(--radius-md)] border px-3.5 py-2.5 text-[14px] leading-snug transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--color-primary)]";
const OPTION_ON =
  "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-text)] font-medium";
const OPTION_OFF =
  "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]";

/** Ordered scale points from `min`..`max`, paired with their config labels. */
function scalePoints(scale: ConfidenceScale): { value: number; label: string }[] {
  const points: { value: number; label: string }[] = [];
  for (let v = scale.min; v <= scale.max; v += 1) {
    points.push({ value: v, label: scale.labels[String(v)] ?? String(v) });
  }
  return points;
}

/**
 * A controlled −2..+2 confidence picker rendered from the pilot config. The
 * selection state is driven by the controlled `value` (not CSS pseudo-classes)
 * so it works identically for the student mobile flow and the readiness survey.
 * MOBILE-FIRST: a single-column stack by default, widening to two columns on
 * `sm` and the full row on `xl`. The visual `<label>` cards wrap `sr-only`
 * radios so keyboard + screen-reader users get real radio-group semantics; the
 * caller supplies the group label (e.g. a `fieldset`/`legend`).
 */
export function ConfidenceScaleInput({
  scale,
  value,
  onChange,
  disabled,
  name,
}: ConfidenceScaleInputProps) {
  const generatedName = useId();
  const groupName = name ?? generatedName;
  const points = scalePoints(scale);

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
      {points.map((point) => {
        const selected = value === point.value;
        return (
          <label
            key={point.value}
            className={cn(OPTION_BASE, selected ? OPTION_ON : OPTION_OFF)}
          >
            <input
              type="radio"
              name={groupName}
              className="sr-only"
              checked={selected}
              disabled={disabled}
              onChange={() => onChange(point.value)}
            />
            <span>{point.label}</span>
          </label>
        );
      })}
    </div>
  );
}
