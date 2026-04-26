"use client";

import { useMemo, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { useCalendarEvents } from "@/hooks/use-calendar-events";
import { WelcomeHero } from "@/components/dashboard/welcome-hero";
import { TodoList } from "@/components/dashboard/todo-list";
import { MiniCalendar } from "@/components/dashboard/mini-calendar";
import { UpcomingSwarms } from "@/components/dashboard/upcoming-swarms";
import { RecentCourses } from "@/components/dashboard/recent-courses";

export default function DashboardPage() {
  const { data: courses, isLoading } = useCourses();
  const events = useCalendarEvents();
  const [selected, setSelected] = useState<Date | undefined>(new Date());

  const courseList: readonly CourseResponse[] = useMemo(
    () => courses ?? [],
    [courses]
  );

  if (isLoading) return <DashboardSkeleton />;

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 px-6 py-6 md:px-10 md:py-10">
      <WelcomeHero />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column (2/3) — to-do + recent courses */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          <TodoList />
          <RecentCourses courses={courseList} />
        </div>

        {/* Right column (1/3) — mini calendar + upcoming */}
        <div className="flex flex-col gap-6">
          <MiniCalendar
            events={events}
            selected={selected}
            onSelectDate={setSelected}
          />
          <UpcomingSwarms events={events} />
        </div>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-8 px-6 py-6 md:px-10 md:py-10">
      <div className="space-y-3 border-b border-[var(--color-border)]/70 pb-6">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-80" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Skeleton className="h-[420px] rounded-[var(--radius-2xl)]" />
          <div className="grid gap-3 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-[var(--radius-2xl)]" />
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-6">
          <Skeleton className="h-[340px] rounded-[var(--radius-2xl)]" />
          <Skeleton className="h-[260px] rounded-[var(--radius-2xl)]" />
        </div>
      </div>
    </div>
  );
}
