"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface SwitchProps {
  /** Controlled on/off state. */
  readonly checked: boolean;
  /** Called with the next state when the user toggles the switch. */
  readonly onCheckedChange: (checked: boolean) => void;
  readonly disabled?: boolean;
  readonly id?: string;
  readonly className?: string;
  readonly "aria-label"?: string;
  readonly "aria-labelledby"?: string;
  readonly "aria-describedby"?: string;
}

/**
 * Accessible toggle switch. Renders a native `<button role="switch">` so that
 * Space/Enter activation and focus handling come for free, with `aria-checked`
 * reflecting state. Styled entirely from design tokens.
 */
export function Switch({
  checked,
  onCheckedChange,
  disabled = false,
  id,
  className,
  ...aria
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-transparent",
        "transition-colors duration-[var(--duration-fast)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        checked
          ? "bg-[var(--color-primary)]"
          : "bg-[var(--color-border-hover)]",
        className,
      )}
      {...aria}
    >
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none inline-block size-5 rounded-full bg-white shadow-sm",
          "transition-transform duration-[var(--duration-fast)]",
          checked ? "translate-x-[22px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}
