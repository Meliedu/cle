import * as React from "react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps extends React.ComponentProps<"header"> {
  /** Primary page title. */
  readonly title: string;
  /** Heading element for the title — `h1` for page tops, `h2` for sections. */
  readonly as?: "h1" | "h2";
  /** Optional supporting sentence beneath the title. */
  readonly description?: string;
  /** Optional breadcrumb / back-link slot, sits above the title. */
  readonly breadcrumb?: ReactNode;
  /** Right-aligned actions (buttons, menus); wraps below the title when narrow. */
  readonly actions?: ReactNode;
}

/**
 * Standard page heading used across every screen: breadcrumb slot, heading
 * title (h1 by default), muted description, and a right-aligned actions
 * cluster that reflows below the title on narrow viewports.
 */
export function PageHeader({
  title,
  as: Heading = "h1",
  description,
  breadcrumb,
  actions,
  className,
  ...rest
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 border-b border-[var(--color-border)]/70 pb-6",
        className
      )}
      {...rest}
    >
      {breadcrumb ? (
        <div className="text-[13px] leading-none text-[var(--color-text-muted)]">
          {breadcrumb}
        </div>
      ) : null}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1.5">
          <Heading className="font-display text-[clamp(1.6rem,1.25rem+1.1vw,2.15rem)] font-semibold leading-[1.1] text-[var(--color-text)]">
            {title}
          </Heading>
          {description ? (
            <p className="max-w-[60ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              {description}
            </p>
          ) : null}
        </div>

        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
            {actions}
          </div>
        ) : null}
      </div>
    </header>
  );
}
