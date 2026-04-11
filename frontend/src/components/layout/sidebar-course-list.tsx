"use client";

import { useState } from "react";
import Link from "next/link";
import { BookOpen, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { CourseResponse } from "@/hooks/use-courses";

interface SidebarCourseListProps {
  readonly courses: readonly CourseResponse[];
  readonly isLoading: boolean;
  readonly activeCourseId: string | null;
  readonly isInstructor: boolean;
  readonly collapsed: boolean;
  readonly onMobileClose?: () => void;
}

export function SidebarCourseList({
  courses,
  isLoading,
  activeCourseId,
  isInstructor,
  collapsed,
  onMobileClose,
}: SidebarCourseListProps) {
  const [dialogOpen, setDialogOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-1 px-2">
        <Skeleton className="h-8 w-full rounded-[var(--radius-md)]" />
        <Skeleton className="h-8 w-full rounded-[var(--radius-md)]" />
      </div>
    );
  }

  return (
    <>
      <div className="space-y-0.5 px-2">
        {courses.map((course) => {
          const isActive = course.id === activeCourseId;
          return (
            <Link
              key={course.id}
              href={`/dashboard/courses/${course.id}?tab=overview`}
              onClick={onMobileClose}
              className={cn(
                "group relative flex items-center gap-2.5 rounded-[var(--radius-md)] px-2.5 py-2 text-sm font-medium transition-all duration-[var(--duration-fast)]",
                collapsed && "justify-center px-2",
                isActive
                  ? "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
              )}
              title={collapsed ? course.name : undefined}
            >
              {isActive && (
                <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--color-primary)]" />
              )}
              <BookOpen className={cn(
                "size-[18px] shrink-0",
                isActive ? "text-[var(--color-primary)]" : "text-[var(--color-text-muted)]"
              )} />
              {!collapsed && (
                <span className="truncate">{course.name}</span>
              )}
            </Link>
          );
        })}

        {isInstructor && (
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-[var(--radius-md)] px-2.5 py-2 text-sm font-medium text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]",
              collapsed && "justify-center px-2"
            )}
          >
            <Plus className="size-[18px] shrink-0" />
            {!collapsed && <span>Add Course</span>}
          </button>
        )}
      </div>

      <CreateCourseDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}
