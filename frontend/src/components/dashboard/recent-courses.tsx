"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowUpRight, KeyRound, Plus } from "lucide-react";
import type { CourseResponse } from "@/hooks/use-courses";
import { CourseRowCard } from "@/components/dashboard/course-row-card";
import { Button } from "@/components/ui/button";
import { useRole } from "@/hooks/use-role";
import { JoinCourseDialog } from "@/components/course/join-course-dialog";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";

interface RecentCoursesProps {
  readonly courses: readonly CourseResponse[];
  readonly limit?: number;
}

export function RecentCourses({ courses, limit = 4 }: RecentCoursesProps) {
  const { isInstructor } = useRole();
  const [joinOpen, setJoinOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const sorted = [...courses].sort((a, b) =>
    b.updated_at.localeCompare(a.updated_at)
  );
  const recent = sorted.slice(0, limit);

  return (
    <section className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
            Recent activity
          </p>
          <h2 className="mt-1 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
            Your courses
          </h2>
        </div>
        {courses.length > limit ? (
          <Link
            href="/dashboard/courses"
            className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] px-3 py-1.5 text-[12px] font-semibold text-[var(--color-text-secondary)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
          >
            View all
            <ArrowUpRight className="size-3.5" strokeWidth={2} />
          </Link>
        ) : null}
      </header>

      {recent.length === 0 ? (
        <EmptyState
          isInstructor={isInstructor}
          onCreate={() => setCreateOpen(true)}
          onJoin={() => setJoinOpen(true)}
        />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {recent.map((course) => (
            <li key={course.id}>
              <CourseRowCard course={course} className="h-full" />
            </li>
          ))}
        </ul>
      )}

      {/* Students join with an enrollment code; only instructors create. */}
      {isInstructor ? (
        <CreateCourseDialog open={createOpen} onOpenChange={setCreateOpen} />
      ) : (
        <JoinCourseDialog open={joinOpen} onOpenChange={setJoinOpen} />
      )}
    </section>
  );
}

interface EmptyStateProps {
  readonly isInstructor: boolean;
  readonly onCreate: () => void;
  readonly onJoin: () => void;
}

function EmptyState({ isInstructor, onCreate, onJoin }: EmptyStateProps) {
  return (
    <div className="rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface-hover)] px-5 py-8 text-center">
      <p className="text-[13px] font-medium text-[var(--color-text-secondary)]">
        No courses yet.
      </p>
      <p className="mx-auto mt-1 max-w-sm text-[12px] text-[var(--color-text-muted)]">
        {isInstructor
          ? "Create your first course to start uploading materials and generating quizzes."
          : "Enter the 8-character enrollment code from your instructor to join your first course."}
      </p>
      <Button
        size="sm"
        className="mt-4 gap-2"
        onClick={isInstructor ? onCreate : onJoin}
      >
        {isInstructor ? (
          <>
            <Plus className="size-4" /> Create a course
          </>
        ) : (
          <>
            <KeyRound className="size-4" /> Enter enrollment code
          </>
        )}
      </Button>
    </div>
  );
}
