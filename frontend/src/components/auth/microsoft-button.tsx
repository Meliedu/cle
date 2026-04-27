"use client";

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

interface MicrosoftButtonProps {
  readonly onClick: () => void;
  readonly loading?: boolean;
  readonly disabled?: boolean;
  readonly label?: string;
}

/**
 * "Continue with Microsoft" — outlined button with the official 4-square
 * Microsoft logo SVG (per Microsoft brand guidelines: f25022 / 7fba00 /
 * 00a4ef / ffb900). The brand mark is the affordance, not the word.
 *
 * Pages gate visibility on NEXT_PUBLIC_MICROSOFT_SSO_ENABLED — this
 * component just renders. It assumes the caller has already decided to
 * show it.
 */
export function MicrosoftButton({
  onClick,
  loading,
  disabled,
  label = "Continue with Microsoft",
}: MicrosoftButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "relative inline-flex h-11 w-full items-center justify-center gap-3 rounded-[var(--radius-md)]",
        "border border-[var(--color-border)] bg-[var(--color-surface)] px-4",
        "text-[14px] font-semibold tracking-[0.01em] text-[var(--color-text)]",
        "outline-none transition-[transform,background-color,border-color,box-shadow] duration-[var(--duration-fast)]",
        "hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)]",
        "focus-visible:shadow-[0_0_0_3px_oklch(60%_0.12_230_/_0.32)]",
        "disabled:cursor-not-allowed disabled:opacity-60",
        "motion-safe:active:scale-[0.98]",
      )}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      ) : (
        <MicrosoftSquares />
      )}
      <span>{label}</span>
    </button>
  );
}

function MicrosoftSquares() {
  return (
    <svg
      viewBox="0 0 21 21"
      width="18"
      height="18"
      role="presentation"
      aria-hidden="true"
      className="shrink-0"
    >
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
