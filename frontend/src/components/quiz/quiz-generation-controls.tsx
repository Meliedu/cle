"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type QuestionType = "multiple_choice" | "true_false";

interface QuestionTypeToggleProps {
  readonly value: readonly QuestionType[];
  readonly onChange: (next: readonly QuestionType[]) => void;
}

export function QuestionTypeToggle({
  value,
  onChange,
}: QuestionTypeToggleProps) {
  const toggle = (t: QuestionType) => {
    const has = value.includes(t);
    const next = has ? value.filter((x) => x !== t) : [...value, t];
    // Always keep at least one type selected.
    onChange(next.length > 0 ? next : value);
  };

  const options: readonly { readonly v: QuestionType; readonly label: string }[] =
    [
      { v: "multiple_choice", label: "Multiple choice" },
      { v: "true_false", label: "True / False" },
    ];

  return (
    <div className="space-y-1.5">
      <Label>Question types</Label>
      <div className="flex gap-2">
        {options.map((opt) => {
          const active = value.includes(opt.v);
          return (
            <button
              key={opt.v}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(opt.v)}
              className={`flex-1 rounded-[var(--radius-md)] border px-3 py-2 text-sm transition-colors ${
                active
                  ? "border-[var(--color-primary)] bg-[var(--color-primary-light)] font-medium"
                  : "border-[var(--color-border)] hover:border-[var(--color-border-hover)]"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-[var(--color-text-muted)]">
        Pick one or both. If you pick both, the generator mixes them.
      </p>
    </div>
  );
}

interface McqOptionCountInputProps {
  readonly value: number;
  readonly onChange: (next: number) => void;
  readonly disabled?: boolean;
}

export function McqOptionCountInput({
  value,
  onChange,
  disabled,
}: McqOptionCountInputProps) {
  return (
    <div className="space-y-1.5">
      <Label>MCQ options</Label>
      <Input
        type="number"
        min={2}
        max={6}
        value={value}
        disabled={disabled}
        onChange={(e) => {
          const parsed = Number(e.target.value) || 4;
          onChange(Math.max(2, Math.min(6, parsed)));
        }}
      />
    </div>
  );
}
