"use client";

import { useUser } from "@clerk/nextjs";
import { BookOpen, Plus, ArrowRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { formatRelativeTime } from "@/lib/format";

function CourseCardSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <div className="flex items-center gap-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-3 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user, isLoaded } = useUser();
  const { data: courses, isLoading: coursesLoading } = useCourses();

  const courseList: readonly CourseResponse[] = courses ?? [];
  const allLoaded = isLoaded && !coursesLoading;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Welcome banner */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-gradient-to-br from-[var(--color-primary-light)] to-[var(--color-surface)] p-6 md:p-8">
        {isLoaded ? (
          <>
            <h1 className="text-2xl font-bold text-[var(--color-text)]">
              Welcome back, {user?.firstName ?? "there"}
            </h1>
            <p className="mt-1 text-[var(--color-text-secondary)]">
              {courseList.length > 0
                ? `You have ${courseList.length} course${courseList.length === 1 ? "" : "s"}.`
                : "Get started by creating or joining a course."}
            </p>
          </>
        ) : (
          <div className="space-y-2">
            <Skeleton className="h-7 w-56" />
            <Skeleton className="h-5 w-72" />
          </div>
        )}
      </section>

      {/* Your Courses */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-[var(--color-text)]">
            Your Courses
          </h2>
          <Link href="/dashboard/courses">
            <Button variant="ghost" size="sm">
              View all
              <ArrowRight className="size-3.5" />
            </Button>
          </Link>
        </div>

        {allLoaded ? (
          courseList.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {courseList.map((course) => (
                <Link
                  key={course.id}
                  href={`/dashboard/courses/${course.id}`}
                >
                  <Card className="group cursor-pointer transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
                    <CardContent className="space-y-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
                            {course.name}
                          </h3>
                          <p className="text-xs text-[var(--color-text-muted)]">
                            {course.code ?? ""}
                          </p>
                        </div>
                        <Badge variant="secondary">
                          {course.language}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
                        <span>{course.semester ?? ""}</span>
                        <span>Updated {formatRelativeTime(course.updated_at)}</span>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center py-12 text-center">
                <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
                  <BookOpen className="size-6 text-[var(--color-primary)]" />
                </div>
                <h3 className="font-semibold text-[var(--color-text)]">
                  No courses yet
                </h3>
                <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                  Create your first course to start uploading materials and
                  generating quizzes for your students.
                </p>
                <Link href="/dashboard/courses">
                  <Button className="mt-4">
                    <Plus className="size-4" />
                    Create Course
                  </Button>
                </Link>
              </CardContent>
            </Card>
          )
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <CourseCardSkeleton key={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
