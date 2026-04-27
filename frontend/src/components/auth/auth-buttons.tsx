"use client";

import { Loader2 } from "lucide-react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  readonly loading?: boolean;
};

const baseClasses = cn(
  "relative inline-flex h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-md)]",
  "px-4 text-[14px] font-semibold tracking-[0.01em]",
  "outline-none transition-[transform,background-color,border-color,color,box-shadow] duration-[var(--duration-fast)]",
  "focus-visible:shadow-[0_0_0_3px_oklch(60%_0.12_230_/_0.32)]",
  "disabled:cursor-not-allowed disabled:opacity-60",
  "motion-safe:active:scale-[0.98]",
);

/** Honey gold solid CTA — primary action on every auth screen. */
export const PrimaryButton = forwardRef<HTMLButtonElement, ButtonProps>(
  function PrimaryButton({ children, loading, disabled, className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={cn(
          baseClasses,
          "bg-[var(--color-primary)] text-[var(--color-text-on-primary)] shadow-[var(--shadow-sm)]",
          "hover:bg-[var(--color-primary-hover)] hover:shadow-[var(--shadow-md)]",
          className,
        )}
        {...rest}
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : null}
        <span>{children}</span>
      </button>
    );
  },
);

/** Warm-bordered outline button — secondary or social actions. */
export const OutlineButton = forwardRef<HTMLButtonElement, ButtonProps>(
  function OutlineButton({ children, loading, disabled, className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        className={cn(
          baseClasses,
          "border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]",
          "hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)]",
          className,
        )}
        {...rest}
      >
        {loading ? (
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        ) : null}
        <span>{children}</span>
      </button>
    );
  },
);
