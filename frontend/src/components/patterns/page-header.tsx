import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  /** Primary page title, rendered as the page's single h1. */
  readonly title: string;
  /** Optional supporting sentence beneath the title. */
  readonly description?: string;
  /** Optional breadcrumb / back-link slot, sits above the title. */
  readonly breadcrumb?: ReactNode;
  /** Right-aligned actions (buttons, menus); wraps below the title when narrow. */
  readonly actions?: ReactNode;
  readonly className?: string;
}

/**
 * Standard page heading used across every screen: breadcrumb slot, h1 title,
 * muted description, and a right-aligned actions cluster that reflows below the
 * title on narrow viewports.
 */
export function PageHeader({
  title,
  description,
  breadcrumb,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex flex-col gap-4 border-b border-[var(--color-border)]/70 pb-6",
        className
      )}
    >
      {breadcrumb ? (
        <div className="text-[13px] leading-none text-[var(--color-text-muted)]">
          {breadcrumb}
        </div>
      ) : null}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1.5">
          <h1 className="text-[clamp(1.5rem,1.2rem+1vw,2rem)] font-semibold leading-[1.15] tracking-tight text-[var(--color-text)]">
            {title}
          </h1>
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
