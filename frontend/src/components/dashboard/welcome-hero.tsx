"use client";

import { useMemo } from "react";
import { useUser } from "@clerk/nextjs";
import { useCourses } from "@/hooks/use-courses";
import { useRole } from "@/hooks/use-role";

function greeting(hour: number): string {
  if (hour < 5) return "Good evening";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function formatDateLong(d: Date): string {
  const weekday = d.toLocaleDateString("en-US", { weekday: "long" });
  const day = d.getDate();
  const month = d.toLocaleDateString("en-US", { month: "long" });
  return `${weekday}, ${day} ${month}`;
}

export function WelcomeHero() {
  const { user } = useUser();
  const { isInstructor } = useRole();
  const { data: courses } = useCourses();

  const now = useMemo(() => new Date(), []);
  const greet = greeting(now.getHours());
  const dateLine = formatDateLong(now);
  const dayNumber = now.getDate();

  const firstName =
    user?.firstName ?? user?.fullName?.split(" ")[0] ?? null;
  const count = courses?.length ?? 0;

  const subtitle = useMemo(() => {
    if (count === 0) {
      return isInstructor
        ? "No courses yet — spin one up to start building materials."
        : "No courses yet — enter an enrollment code to join your first one.";
    }
    const noun = count === 1 ? "course" : "courses";
    return isInstructor
      ? `${count} ${noun} in your teaching roster today.`
      : `${count} ${noun} on your desk today.`;
  }, [count, isInstructor]);

  return (
    <section className="flex flex-col gap-4 border-b border-[var(--color-border)]/70 pb-6 md:flex-row md:items-end md:justify-between">
      <div className="space-y-1.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          {greet}
        </p>
        <h1 className="text-[clamp(1.75rem,1.3rem+1vw,2.25rem)] font-semibold leading-[1.1] tracking-tight text-[var(--color-text)]">
          {firstName ? `Welcome back, ${firstName}.` : "Welcome back."}
        </h1>
        <p className="max-w-[48ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          {subtitle}
        </p>
      </div>

      <div
        className="flex items-center gap-4"
        aria-label={`Today is ${dateLine}`}
      >
        <div className="text-right">
          <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-muted)]">
            Today
          </p>
          <p className="mt-0.5 text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
            {dateLine}
          </p>
        </div>
        <div
          className="flex size-12 shrink-0 flex-col items-center justify-center rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)]"
          aria-hidden="true"
        >
          <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--color-primary)]">
            {now.toLocaleDateString("en-US", { month: "short" })}
          </span>
          <span className="-mt-0.5 text-[18px] font-semibold leading-none text-[var(--color-text)]">
            {dayNumber}
          </span>
        </div>
      </div>
    </section>
  );
}
