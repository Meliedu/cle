"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useUser } from "@clerk/nextjs";
import { BookOpen, Plus, Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { formatRelativeTime } from "@/lib/format";

function languageBadgeVariant(
  language: string
): "default" | "secondary" | "outline" {
  switch (language) {
    case "Chinese":
      return "default";
    case "English":
      return "secondary";
    default:
      return "outline";
  }
}

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

function isInstructorEmail(email: string | undefined): boolean {
  if (!email) return false;
  return email.endsWith("@ust.hk");
}

export default function CoursesPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const { user, isLoaded: userLoaded } = useUser();
  const { data: courses, isLoading: coursesLoading } = useCourses();

  const isLoaded = userLoaded && !coursesLoading;
  const isInstructor = isInstructorEmail(
    user?.primaryEmailAddress?.emailAddress
  );

  const courseList: readonly CourseResponse[] = courses ?? [];

  const filteredCourses = useMemo(() => {
    if (!searchQuery) return courseList;
    const q = searchQuery.toLowerCase();
    return courseList.filter(
      (course) =>
        course.name.toLowerCase().includes(q) ||
        (course.code?.toLowerCase().includes(q) ?? false)
    );
  }, [courseList, searchQuery]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)]">
            Courses
          </h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            Manage and browse your courses
          </p>
        </div>
        {isInstructor && (
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="size-4" />
            Create Course
          </Button>
        )}
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <Input
          placeholder="Search courses..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8"
        />
      </div>

      {/* Course grid */}
      {isLoaded ? (
        filteredCourses.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredCourses.map((course) => (
              <Link
                key={course.id}
                href={`/dashboard/courses/${course.id}`}
              >
                <Card className="group h-full cursor-pointer transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]">
                  <CardContent className="flex h-full flex-col justify-between space-y-3">
                    <div>
                      <div className="mb-1 flex items-start justify-between">
                        <div>
                          <h3 className="font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] group-hover:text-[var(--color-primary)]">
                            {course.name}
                          </h3>
                          <p className="text-xs text-[var(--color-text-muted)]">
                            {course.code ?? ""}
                          </p>
                        </div>
                        <Badge
                          variant={languageBadgeVariant(course.language)}
                        >
                          {course.language}
                        </Badge>
                      </div>
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
              <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
                <BookOpen className="size-6 text-[var(--color-primary)]" />
              </div>
              <h3 className="font-semibold text-[var(--color-text)]">
                {searchQuery ? "No courses found" : "No courses yet"}
              </h3>
              <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                {searchQuery
                  ? `No courses match "${searchQuery}". Try a different search term.`
                  : "Create your first course to start building learning materials."}
              </p>
              {!searchQuery && isInstructor && (
                <Button className="mt-4" onClick={() => setDialogOpen(true)}>
                  <Plus className="size-4" />
                  Create Course
                </Button>
              )}
            </CardContent>
          </Card>
        )
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CourseCardSkeleton key={i} />
          ))}
        </div>
      )}

      <CreateCourseDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
