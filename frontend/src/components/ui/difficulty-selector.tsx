"use client";

import { useRef, type KeyboardEvent } from "react";
import { Label } from "@/components/ui/label";

export type Difficulty = "easy" | "medium" | "hard" | "mixed";

export const DIFFICULTY_OPTIONS: readonly Difficulty[] = [
  "easy",
  "medium",
  "hard",
  "mixed",
] as const;

interface DifficultySelectorProps {
  readonly value: Difficulty;
  readonly onChange: (next: Difficulty) => void;
  readonly label?: string;
  readonly disabled?: boolean;
  readonly id?: string;
}

export function DifficultySelector({
  value,
  onChange,
  label = "Difficulty",
  disabled = false,
  id,
}: DifficultySelectorProps) {
  const buttonsRef = useRef<(HTMLButtonElement | null)[]>([]);

  const focusIndex = (nextIndex: number) => {
    const total = DIFFICULTY_OPTIONS.length;
    const bounded = ((nextIndex % total) + total) % total;
    const btn = buttonsRef.current[bounded];
    if (btn) {
      btn.focus();
      onChange(DIFFICULTY_OPTIONS[bounded]!);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>, idx: number) => {
    if (disabled) return;
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
        e.preventDefault();
        focusIndex(idx + 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        e.preventDefault();
        focusIndex(idx - 1);
        break;
      case "Home":
        e.preventDefault();
        focusIndex(0);
        break;
      case "End":
        e.preventDefault();
        focusIndex(DIFFICULTY_OPTIONS.length - 1);
        break;
      default:
        break;
    }
  };

  const activeIndex = Math.max(0, DIFFICULTY_OPTIONS.indexOf(value));

  return (
    <div className="space-y-1.5">
      {label && <Label htmlFor={id}>{label}</Label>}
      <div
        id={id}
        role="radiogroup"
        aria-label={label}
        className="grid grid-cols-4 gap-2"
      >
        {DIFFICULTY_OPTIONS.map((d, idx) => {
          const active = value === d;
          return (
            <button
              key={d}
              ref={(el) => {
                buttonsRef.current[idx] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={idx === activeIndex ? 0 : -1}
              disabled={disabled}
              onClick={() => onChange(d)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm capitalize transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] disabled:cursor-not-allowed disabled:opacity-60 ${
                active
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] font-medium"
                  : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
              }`}
            >
              {d}
            </button>
          );
        })}
      </div>
    </div>
  );
}
