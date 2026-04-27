interface DividerLabelProps {
  readonly label?: string;
}

/**
 * Editorial "or" rule. Two hairline strokes flanking a small uppercase
 * label that matches the dashboard's metadata typography.
 */
export function DividerLabel({ label = "or" }: DividerLabelProps) {
  return (
    <div
      role="separator"
      aria-orientation="horizontal"
      className="my-5 flex items-center gap-3"
    >
      <span className="h-px flex-1 bg-[var(--color-border)]" />
      <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-muted)]">
        {label}
      </span>
      <span className="h-px flex-1 bg-[var(--color-border)]" />
    </div>
  );
}
