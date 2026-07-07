"use client";

import { useCallback } from "react";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { ConfidenceScale, ReadinessQuestion } from "@/lib/pilot-config";

/**
 * A single answer value, shaped by the question `kind`:
 * - `single_choice` → the chosen option string (or `null`)
 * - `multi_choice`  → the chosen option strings
 * - `scale`         → the chosen scale point (a number, or `null`)
 * - `short_text`    → the typed string
 */
export type ReadinessAnswer = string | readonly string[] | number | null;

/** The empty answer for a question kind — used to seed the phase's answer map. */
export function emptyAnswer(kind: ReadinessQuestion["kind"]): ReadinessAnswer {
  if (kind === "multi_choice") return [];
  if (kind === "short_text") return "";
  return null;
}

interface ReadinessQuestionFieldProps {
  readonly question: ReadinessQuestion;
  /** The pilot's confidence scale (drives `scale` questions; −2..+2 in CLE). */
  readonly confidenceScale: ConfidenceScale;
  readonly value: ReadinessAnswer;
  readonly onChange: (value: ReadinessAnswer) => void;
  readonly disabled?: boolean;
}

/** Ordered scale points from `min`..`max`, paired with their config labels. */
function scalePoints(scale: ConfidenceScale): { value: number; label: string }[] {
  const points: { value: number; label: string }[] = [];
  for (let v = scale.min; v <= scale.max; v += 1) {
    points.push({ value: v, label: scale.labels[String(v)] ?? String(v) });
  }
  return points;
}

const OPTION_BASE =
  "flex cursor-pointer items-center gap-2.5 rounded-[var(--radius-md)] border px-3.5 py-2.5 text-[14px] leading-snug transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--color-primary)]";
const OPTION_ON =
  "border-[var(--color-primary)] bg-[var(--color-primary-light)] text-[var(--color-text)] font-medium";
const OPTION_OFF =
  "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]";

/**
 * A controlled, config-driven input for one readiness question. The rendering
 * branches on `question.kind`; the question text, options, and scale labels all
 * come from the pilot config so a different pilot yields different questions
 * with no code change. Choice/scale groups are wrapped in a `fieldset`/`legend`
 * for screen-reader grouping; the visual selection state is driven by the
 * controlled `value`, not CSS pseudo-classes.
 */
export function ReadinessQuestionField({
  question,
  confidenceScale,
  value,
  onChange,
  disabled,
}: ReadinessQuestionFieldProps) {
  const toggleMulti = useCallback(
    (option: string) => {
      const current = Array.isArray(value) ? value : [];
      const next = current.includes(option)
        ? current.filter((o) => o !== option)
        : [...current, option];
      onChange(next);
    },
    [onChange, value]
  );

  if (question.kind === "short_text") {
    const fieldId = `rq-${question.id}`;
    return (
      <div className="space-y-2">
        <label
          htmlFor={fieldId}
          className="block text-[14px] font-medium leading-snug text-[var(--color-text)]"
        >
          {question.prompt}
        </label>
        <Textarea
          id={fieldId}
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    );
  }

  if (question.kind === "scale") {
    const points = scalePoints(confidenceScale);
    return (
      <fieldset className="space-y-2.5" disabled={disabled}>
        <legend className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
          {question.prompt}
        </legend>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {points.map((point) => {
            const selected = value === point.value;
            return (
              <label
                key={point.value}
                className={cn(OPTION_BASE, selected ? OPTION_ON : OPTION_OFF)}
              >
                <input
                  type="radio"
                  name={`rq-${question.id}`}
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
      </fieldset>
    );
  }

  // single_choice | multi_choice — both render option cards; multi keeps a list.
  const isMulti = question.kind === "multi_choice";
  return (
    <fieldset className="space-y-2.5" disabled={disabled}>
      <legend className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
        {question.prompt}
      </legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {question.options.map((option) => {
          const selected = isMulti
            ? Array.isArray(value) && value.includes(option)
            : value === option;
          return (
            <label
              key={option}
              className={cn(OPTION_BASE, selected ? OPTION_ON : OPTION_OFF)}
            >
              <input
                type={isMulti ? "checkbox" : "radio"}
                name={`rq-${question.id}`}
                className="sr-only"
                checked={selected}
                disabled={disabled}
                onChange={() =>
                  isMulti ? toggleMulti(option) : onChange(option)
                }
              />
              <span>{option}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
