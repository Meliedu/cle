"use client";

import { useState, useRef, useCallback, useEffect } from "react";

interface QuizItemProps {
  readonly item: {
    readonly question_text: string;
    readonly options: Record<string, string>;
  };
  readonly onAnswer: (params: {
    answer: string;
    time_taken_ms: number;
  }) => void;
  readonly disabled?: boolean;
}

const OPTION_LABELS = ["A", "B", "C", "D"] as const;

export function QuizItem({ item, onAnswer, disabled = false }: QuizItemProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const mountTimeRef = useRef<number>(Date.now());

  // Reset selected state and timer when item changes
  useEffect(() => {
    setSelected(null);
    mountTimeRef.current = Date.now();
  }, [item.question_text]);

  const handleSelect = useCallback(
    (label: string) => {
      if (disabled || selected !== null) return;

      setSelected(label);
      const elapsed = Date.now() - mountTimeRef.current;
      onAnswer({ answer: label, time_taken_ms: elapsed });
    },
    [disabled, selected, onAnswer]
  );

  const optionEntries = OPTION_LABELS.filter(
    (label) => label in item.options
  ).map((label) => ({
    label,
    text: item.options[label],
  }));

  return (
    <div className="space-y-6">
      <h2
        data-testid="question-text"
        className="text-lg font-semibold leading-relaxed text-[var(--color-text)]"
      >
        {item.question_text}
      </h2>

      <div className="space-y-3">
        {optionEntries.map((option) => {
          const isSelected = selected === option.label;
          const isDisabled = disabled || selected !== null;

          return (
            <button
              key={option.label}
              type="button"
              disabled={isDisabled}
              onClick={() => handleSelect(option.label)}
              className="flex w-full items-center gap-3 rounded-[var(--radius-lg)] border p-4 text-left transition-all duration-[var(--duration-fast)] outline-none focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30 disabled:cursor-default"
              style={{
                minHeight: "48px",
                borderColor: isSelected
                  ? "var(--color-primary)"
                  : "var(--color-border)",
                backgroundColor: isSelected
                  ? "var(--color-primary-light)"
                  : "var(--color-surface)",
                opacity: isDisabled && !isSelected ? 0.6 : 1,
              }}
              onMouseEnter={(e) => {
                if (!isDisabled) {
                  e.currentTarget.style.borderColor =
                    "var(--color-border-hover)";
                  e.currentTarget.style.backgroundColor =
                    "var(--color-surface-hover)";
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = "var(--color-border)";
                  e.currentTarget.style.backgroundColor =
                    "var(--color-surface)";
                }
              }}
            >
              <span
                className="flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold transition-colors duration-[var(--duration-fast)]"
                style={{
                  borderColor: isSelected
                    ? "var(--color-primary)"
                    : "var(--color-border)",
                  backgroundColor: isSelected
                    ? "var(--color-primary)"
                    : "transparent",
                  color: isSelected ? "white" : "var(--color-text-muted)",
                }}
              >
                {option.label}
              </span>
              <span
                className="flex-1 text-sm font-medium"
                style={{
                  color: isSelected
                    ? "var(--color-primary)"
                    : "var(--color-text)",
                }}
              >
                {option.text}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
