"use client";

import { useState } from "react";
import Link from "next/link";
import { BookOpen, Plus, KeyRound } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { useRole } from "@/hooks/use-role";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";
import { JoinCourseDialog } from "@/components/course/join-course-dialog";
import { CanvasCoursePicker } from "@/components/canvas/canvas-course-picker";
import { formatRelativeTime } from "@/lib/format";

export default function DashboardPage() {
  const { isInstructor } = useRole();
  const { data: courses, isLoading } = useCourses();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);

  const courseList: readonly CourseResponse[] = courses ?? [];

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-[var(--color-text)]">
          Your Courses
        </h1>
        {isInstructor ? (
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            New Course
          </Button>
        ) : (
          <Button onClick={() => setJoinOpen(true)}>
            <KeyRound className="size-4" />
            Join Course
          </Button>
        )}
      </div>

      {isInstructor && <CanvasCoursePicker />}

      {courseList.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {courseList.map((course) => (
            <Link
              key={course.id}
              href={`/dashboard/courses/${course.id}?tab=overview`}
            >
              <Card className="group h-full cursor-pointer transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
                <CardContent className="flex h-full flex-col justify-between space-y-3">
                  <div>
                    <div className="mb-1 flex items-start justify-between">
                      <h3 className="font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
                        {course.name}
                      </h3>
                      <Badge variant="secondary">{course.language}</Badge>
                    </div>
                    {course.code && (
                      <p className="text-xs text-[var(--color-text-muted)]">{course.code}</p>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-xs text-[var(--color-text-muted)]">
                    <span>Updated {formatRelativeTime(course.updated_at)}</span>
                    <span>{course.semester ?? ""}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
              <BookOpen className="size-7 text-[var(--color-primary)]" />
            </div>
            <h2 className="text-lg font-semibold text-[var(--color-text)]">
              No courses yet
            </h2>
            <p className="mt-2 max-w-sm text-sm text-[var(--color-text-muted)]">
              {isInstructor
                ? "Create your first course to start uploading materials and generating quizzes."
                : "Ask your instructor for the 8-character course code, then enter it to join."}
            </p>
            {isInstructor ? (
              <Button className="mt-6" onClick={() => setDialogOpen(true)}>
                <Plus className="size-4" />
                Create Your First Course
              </Button>
            ) : (
              <Button className="mt-6" onClick={() => setJoinOpen(true)}>
                <KeyRound className="size-4" />
                Enter Enrollment Code
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      <CreateCourseDialog open={dialogOpen} onOpenChange={setDialogOpen} />
      <JoinCourseDialog open={joinOpen} onOpenChange={setJoinOpen} />
    </div>
  );
}
