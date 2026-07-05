"use client";

import { format, parseISO } from "date-fns";
import { CalendarClock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DashboardPreviewEvent } from "@/components/dashboard/dashboard-preview-events";

interface UpcomingSwarmsProps {
  readonly events: readonly DashboardPreviewEvent[];
  readonly limit?: number;
  readonly title?: string;
  readonly showPreviewBadge?: boolean;
  readonly className?: string;
  readonly emptyLabel?: string;
}

const TONE_CLASSES: Record<DashboardPreviewEvent["color"], string> = {
  honey:
    "bg-[var(--color-primary-light)] text-[var(--color-text-on-primary)]",
  coral: "bg-[oklch(88%_0.07_35)] text-[oklch(30%_0.05_35)]",
  salt: "bg-[var(--color-accent-light)] text-[var(--color-accent-hover)]",
};

export function UpcomingSwarms({
  events,
  limit = 5,
  title = "Upcoming",
  showPreviewBadge = true,
  className,
  emptyLabel = "No upcoming events.",
}: UpcomingSwarmsProps) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const visible = events
    .filter((e) => parseISO(e.date) >= today)
    .slice(0, limit);

  return (
    <section
      className={cn(
        "flex h-full flex-col rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)]",
        className
      )}
    >
      <header className="flex items-center justify-between gap-3 border-b border-[var(--color-border)]/80 px-5 py-4">
        <div className="flex items-center gap-2">
          <CalendarClock
            className="size-[18px] text-[var(--color-accent)]"
            strokeWidth={1.85}
          />
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {title}
          </h2>
        </div>
        {showPreviewBadge ? (
          <span className="rounded-[var(--radius-pill)] bg-[var(--color-accent-light)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-accent)]">
            Preview
          </span>
        ) : null}
      </header>

      {visible.length === 0 ? (
        <div className="flex flex-1 items-center justify-center px-5 py-10 text-[13px] text-[var(--color-text-muted)]">
          {emptyLabel}
        </div>
      ) : (
        <ul className="flex-1 divide-y divide-[var(--color-border)]/70">
          {visible.map((event) => {
            const d = parseISO(event.date);
            return (
              <li key={event.id}>
                <button
                  type="button"
                  className="flex w-full items-start gap-4 px-5 py-3.5 text-left transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
                >
                  <div
                    className={cn(
                      "flex size-12 shrink-0 flex-col items-center justify-center rounded-[var(--radius-lg)] font-semibold leading-none",
                      TONE_CLASSES[event.color]
                    )}
                    aria-hidden="true"
                  >
                    <span className="text-[9px] uppercase tracking-[0.12em] opacity-70">
                      {format(d, "MMM")}
                    </span>
                    <span className="mt-0.5 text-[17px]">
                      {format(d, "d")}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-semibold text-[var(--color-text)]">
                      {event.title}
                    </p>
                    {event.subtitle ? (
                      <p className="mt-0.5 truncate text-[12px] text-[var(--color-text-muted)]">
                        {event.subtitle}
                      </p>
                    ) : (
                      <p className="mt-0.5 text-[12px] text-[var(--color-text-muted)]">
                        {event.kind === "todo"
                          ? event.done
                            ? "Completed task"
                            : "Personal task"
                          : format(d, "EEEE")}
                      </p>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
