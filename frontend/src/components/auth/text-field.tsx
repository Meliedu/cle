"use client";

import { Eye, EyeOff } from "lucide-react";
import { forwardRef, useId, useState } from "react";

import { FieldError } from "@/components/auth/field-error";
import { cn } from "@/lib/utils";

type BaseProps = Omit<
  React.InputHTMLAttributes<HTMLInputElement>,
  "id" | "type"
>;

interface TextFieldProps extends BaseProps {
  readonly label: string;
  readonly type?: "text" | "email" | "password";
  readonly helperText?: React.ReactNode;
  readonly error?: string | null;
  readonly endAdornment?: React.ReactNode;
}

/**
 * Labeled text input with persistent above-field label, salt-blue focus
 * ring, optional helper text, inline error wired via aria-describedby, and
 * a 44pt eye-toggle button on type="password".
 *
 * Validation is left to the caller — this primitive is presentational and
 * accessible only. Pages drive blur-validation themselves.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(
  function TextField(
    {
      label,
      type = "text",
      helperText,
      error,
      endAdornment,
      className,
      required,
      ...rest
    },
    ref,
  ) {
    const reactId = useId();
    const inputId = rest.name ? `${rest.name}-${reactId}` : reactId;
    const helperId = helperText ? `${inputId}-helper` : undefined;
    const errorId = `${inputId}-error`;
    const [revealed, setRevealed] = useState(false);

    const isPassword = type === "password";
    const inputType = isPassword && revealed ? "text" : type;

    const describedBy =
      [helperId, error ? errorId : undefined].filter(Boolean).join(" ") ||
      undefined;

    return (
      <div className={cn("space-y-1.5", className)}>
        <label
          htmlFor={inputId}
          className="flex items-center justify-between text-[12px] font-medium tracking-[0.04em] text-[var(--color-text-secondary)]"
        >
          <span>
            {label}
            {required ? (
              <span aria-hidden="true" className="ml-0.5 text-[var(--color-error)]">
                *
              </span>
            ) : null}
          </span>
          {helperText ? (
            <span
              id={helperId}
              className="text-[11px] font-normal tracking-normal text-[var(--color-text-muted)]"
            >
              {helperText}
            </span>
          ) : null}
        </label>

        <div className="relative">
          <input
            ref={ref}
            id={inputId}
            type={inputType}
            required={required}
            aria-invalid={Boolean(error) || undefined}
            aria-describedby={describedBy}
            className={cn(
              "block w-full rounded-[var(--radius-md)] border bg-[var(--color-surface)]",
              "px-3.5 text-[15px] leading-tight text-[var(--color-text)] placeholder:text-[var(--color-text-muted)]",
              "h-11 outline-none transition-[border-color,box-shadow,background-color] duration-[var(--duration-fast)]",
              "focus-visible:bg-[var(--color-surface)]",
              error
                ? "border-[var(--color-error)] focus-visible:border-[var(--color-error)] focus-visible:shadow-[0_0_0_3px_oklch(55%_0.22_25_/_0.18)]"
                : "border-[var(--color-border)] hover:border-[var(--color-border-hover)] focus-visible:border-[var(--color-accent)] focus-visible:shadow-[0_0_0_3px_oklch(60%_0.12_230_/_0.18)]",
              isPassword && "pr-12",
              endAdornment && !isPassword && "pr-11",
            )}
            {...rest}
          />

          {isPassword ? (
            <button
              type="button"
              onClick={() => setRevealed((value) => !value)}
              aria-label={revealed ? "Hide password" : "Show password"}
              aria-pressed={revealed}
              tabIndex={-1}
              className="absolute inset-y-0 right-0 inline-flex w-12 items-center justify-center text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text)] focus-visible:text-[var(--color-text)] focus-visible:outline-none"
            >
              {revealed ? (
                <EyeOff className="size-4" aria-hidden="true" />
              ) : (
                <Eye className="size-4" aria-hidden="true" />
              )}
            </button>
          ) : null}

          {endAdornment && !isPassword ? (
            <div className="absolute inset-y-0 right-3 flex items-center text-[var(--color-text-muted)]">
              {endAdornment}
            </div>
          ) : null}
        </div>

        <FieldError id={errorId}>{error}</FieldError>
      </div>
    );
  },
);
