import { Inbox, type LucideIcon } from "lucide-react";
import * as React from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { toneStyles } from "./tones";

export type EmptyStateVariant = "empty" | "waiting";

export interface EmptyStateProps extends React.ComponentProps<"div"> {
  /** `empty` = nothing here yet; `waiting` = pending / processing. */
  readonly variant?: EmptyStateVariant;
  /** Headline shown beneath the icon. */
  readonly title: string;
  /** Optional supporting sentence explaining the state or next step. */
  readonly reason?: string;
  /** Optional primary action (e.g. a create button). */
  readonly action?: ReactNode;
  /** Override the default icon (`Inbox` for empty, `Clock` for waiting). */
  readonly icon?: LucideIcon;
}

/**
 * Centered placeholder for empty or pending regions: icon in a soft circle,
 * title, reason, and an optional action. The `waiting` variant borrows the
 * shared `waiting` tone colors so it matches `StateBanner`.
 */
export function EmptyState({
  variant = "empty",
  title,
  reason,
  action,
  icon,
  className,
  ...rest
}: EmptyStateProps) {
  const isWaiting = variant === "waiting";
  const Icon = icon ?? (isWaiting ? toneStyles.waiting.Icon : Inbox);
  const circle = isWaiting
    ? toneStyles.waiting.container
    : "border-[var(--color-border)] bg-[var(--color-surface-hover)]";
  const iconColor = isWaiting
    ? toneStyles.waiting.icon
    : "text-[var(--color-text-muted)]";

  return (
    <div
      data-variant={variant}
      className={cn(
        "flex flex-col items-center justify-center gap-4 px-6 py-16 text-center",
        className
      )}
      {...rest}
    >
      <div
        className={cn(
          "flex size-14 items-center justify-center rounded-full border",
          circle
        )}
      >
        <Icon
          aria-hidden="true"
          strokeWidth={1.75}
          className={cn("size-6", iconColor)}
        />
      </div>

      <div className="space-y-1.5">
        <h3 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {title}
        </h3>
        {reason ? (
          <p className="mx-auto max-w-[42ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {reason}
          </p>
        ) : null}
      </div>

      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  );
}
