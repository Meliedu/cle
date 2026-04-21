"use client";

type Level = "easy" | "medium" | "hard" | "mixed" | string;

interface DifficultyBadgeProps {
  readonly value: Level | null | undefined;
  readonly size?: "xs" | "sm";
}

interface StyleDef {
  readonly bg: string;
  readonly fg: string;
  readonly border: string;
}

// Uses existing oklch design tokens so the palette stays on-brand across
// light/dark themes — no hardcoded colours.
const STYLES: Record<string, StyleDef> = {
  easy: {
    bg: "var(--color-success-light)",
    fg: "var(--color-success)",
    border: "var(--color-success)",
  },
  medium: {
    bg: "var(--color-warning-light)",
    fg: "var(--color-warning)",
    border: "var(--color-warning)",
  },
  hard: {
    bg: "oklch(93% 0.05 25)",
    fg: "var(--color-error)",
    border: "var(--color-error)",
  },
  mixed: {
    bg: "var(--color-primary-light)",
    fg: "var(--color-primary)",
    border: "var(--color-primary)",
  },
};

const FALLBACK: StyleDef = {
  bg: "var(--color-surface-hover)",
  fg: "var(--color-text-muted)",
  border: "var(--color-border)",
};

export function DifficultyBadge({ value, size = "xs" }: DifficultyBadgeProps) {
  if (!value) return null;
  const key = value.toLowerCase();
  const style = STYLES[key] ?? FALLBACK;
  const sizeCls =
    size === "sm" ? "text-xs px-2 py-0.5" : "text-[10px] px-1.5 py-0.5";
  return (
    <span
      className={`inline-flex items-center rounded-[var(--radius-sm)] border font-medium uppercase tracking-wide ${sizeCls}`}
      style={{
        backgroundColor: style.bg,
        color: style.fg,
        borderColor: style.border,
      }}
      aria-label={`Difficulty: ${value}`}
    >
      {value}
    </span>
  );
}
