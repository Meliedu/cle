"use client";

import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { useCourses } from "@/hooks/use-courses";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CalendarEvent } from "@/lib/curriculum-types";

function startOfWeek(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - x.getDay());
  return x;
}

interface DecoratedEvent extends CalendarEvent {
  readonly courseName: string;
  readonly courseId: string;
}

const KIND_DOT: Record<DecoratedEvent["kind"], string> = {
  meeting: "bg-[var(--color-primary)]",
  assignment: "bg-[oklch(70%_0.13_35)]",
};

export default function CalendarPage() {
  const { getToken } = useAuth();
  const { data: courses = [] } = useCourses();

  const range = useMemo(() => {
    const from = startOfWeek(new Date());
    const to = new Date(from);
    to.setDate(from.getDate() + 7);
    return { from, to };
  }, []);

  const queries = useQueries({
    queries: courses.map((c) => ({
      queryKey: [
        "calendar",
        c.id,
        range.from.toISOString(),
        range.to.toISOString(),
      ],
      queryFn: async (): Promise<DecoratedEvent[]> => {
        const token = await getToken({ template: "backend" });
        if (!token) throw new Error("Not authenticated");
        const params = new URLSearchParams({
          from_date: range.from.toISOString(),
          to_date: range.to.toISOString(),
        });
        const res = await apiFetch<ApiEnvelope<CalendarEvent[]>>(
          `/courses/${c.id}/calendar?${params}`,
          { token }
        );
        return res.data.map((e) => ({
          ...e,
          courseName: c.name,
          courseId: c.id,
        }));
      },
    })),
  });

  const isLoading = queries.some((q) => q.isLoading);
  const events: DecoratedEvent[] = queries
    .flatMap((q) => q.data ?? [])
    .sort((a, b) => a.at.localeCompare(b.at));

  const weekLabel = range.from.toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:gap-8 md:px-10 md:py-10">
      <header className="flex flex-col gap-2 border-b border-[var(--color-border)]/70 pb-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          Overview
        </p>
        <h1 className="text-[clamp(1.75rem,1.3rem+1vw,2.25rem)] font-semibold leading-[1.1] tracking-tight text-[var(--color-text)]">
          Calendar
        </h1>
        <p className="max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          Week of {weekLabel} — meetings and assignments across all your courses.
        </p>
      </header>

      {isLoading ? (
        <ul className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <li
              key={i}
              className="h-14 animate-pulse rounded-[var(--radius-xl)] bg-[var(--color-surface-hover)]"
            />
          ))}
        </ul>
      ) : events.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] py-16 text-center">
          <p className="text-[15px] font-semibold text-[var(--color-text)]">
            Nothing scheduled this week
          </p>
          <p className="text-[13px] text-[var(--color-text-muted)]">
            Meetings and due assignments will appear here.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2">
          {events.map((e) => (
            <li
              key={`${e.kind}-${e.id}`}
              className="flex items-center gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3.5 shadow-sm transition-shadow duration-[var(--duration-fast)] hover:shadow-md"
            >
              <span
                className={`size-2 shrink-0 rounded-full ${KIND_DOT[e.kind]}`}
                aria-hidden="true"
              />
              <span className="w-40 shrink-0 text-[13px] text-[var(--color-text-muted)]">
                {new Date(e.at).toLocaleString(undefined, {
                  weekday: "short",
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
              <span className="flex-1 text-[14px] font-semibold text-[var(--color-text)]">
                {e.title}
              </span>
              <span className="shrink-0 rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-secondary)]">
                {e.kind === "meeting" ? "Meeting" : (e.assignment_kind ?? "Assignment")}
              </span>
              <span className="shrink-0 text-[12px] text-[var(--color-text-muted)]">
                {e.courseName}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
