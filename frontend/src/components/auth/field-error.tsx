import { cn } from "@/lib/utils";

interface FieldErrorProps {
  readonly id?: string;
  readonly children?: React.ReactNode;
  readonly className?: string;
}

/**
 * Inline form error. Always renders into the DOM (so screen readers can
 * announce updates via aria-live), only visible when `children` is non-empty.
 */
export function FieldError({ id, children, className }: FieldErrorProps) {
  const hasError = Boolean(children);
  return (
    <p
      id={id}
      role="alert"
      aria-live="polite"
      className={cn(
        "min-h-[1.1rem] text-[13px] leading-tight text-[var(--color-error)]",
        "transition-opacity duration-[var(--duration-fast)]",
        hasError ? "opacity-100" : "opacity-0",
        className,
      )}
    >
      {children ?? " "}
    </p>
  );
}
