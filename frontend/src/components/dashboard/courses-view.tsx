"use client";

import { useCallback, useMemo, useState } from "react";
import { BookOpen, KeyRound, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCourses, type CourseResponse } from "@/hooks/use-courses";
import { useRole } from "@/hooks/use-role";
import { CreateCourseDialog } from "@/components/course/create-course-dialog";
import { JoinCourseDialog } from "@/components/course/join-course-dialog";
import { CanvasCoursePicker } from "@/components/canvas/canvas-course-picker";
import { CANVAS_ENABLED } from "@/lib/features";
import { CourseFilters } from "@/components/dashboard/course-filters";
import { CourseRowCard } from "@/components/dashboard/course-row-card";

interface LanguageFacet {
  readonly value: string;
  readonly label: string;
  readonly flag: string;
  readonly count: number;
}

const LANGUAGE_FLAGS: Record<string, string> = {
  english: "🇬🇧",
  spanish: "🇪🇸",
  french: "🇫🇷",
  german: "🇩🇪",
  chinese: "🇨🇳",
  mandarin: "🇨🇳",
  cantonese: "🇭🇰",
  japanese: "🇯🇵",
  korean: "🇰🇷",
  portuguese: "🇵🇹",
  italian: "🇮🇹",
  arabic: "🇸🇦",
  russian: "🇷🇺",
  dutch: "🇳🇱",
};

function flagFor(language: string): string {
  const key = language.trim().toLowerCase();
  return LANGUAGE_FLAGS[key] ?? "✶";
}

function titleCase(input: string): string {
  return input
    .trim()
    .split(/\s+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

/**
 * Course list composition shared by every role lane (`/teacher/courses`,
 * `/student/courses`, and the legacy `/dashboard/courses`). Instructor-only
 * affordances (create, Canvas import) branch on the backend-authoritative
 * role; the backend still enforces access on every endpoint.
 */
export function CoursesView() {
  const { isInstructor } = useRole();
  const { data: courses, isLoading } = useCourses();
  const [createOpen, setCreateOpen] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);
  const [activeLanguage, setActiveLanguage] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const courseList: readonly CourseResponse[] = useMemo(
    () => courses ?? [],
    [courses]
  );

  const languageFacets: readonly LanguageFacet[] = useMemo(() => {
    const buckets = new Map<string, LanguageFacet>();
    for (const course of courseList) {
      const key = course.language.trim().toLowerCase();
      if (!key) continue;
      const existing = buckets.get(key);
      if (existing) {
        buckets.set(key, { ...existing, count: existing.count + 1 });
      } else {
        buckets.set(key, {
          value: key,
          label: titleCase(course.language),
          flag: flagFor(course.language),
          count: 1,
        });
      }
    }
    return Array.from(buckets.values()).sort((a, b) => b.count - a.count);
  }, [courseList]);

  const filteredCourses = useMemo(() => {
    const q = query.trim().toLowerCase();
    return courseList.filter((course) => {
      if (
        activeLanguage &&
        course.language.trim().toLowerCase() !== activeLanguage
      ) {
        return false;
      }
      if (q) {
        const haystack = `${course.name} ${course.code ?? ""} ${
          course.description ?? ""
        }`.toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [courseList, activeLanguage, query]);

  const handleCreate = useCallback(() => setCreateOpen(true), []);
  const handleJoin = useCallback(() => setJoinOpen(true), []);
  const resetFilters = useCallback(() => {
    setActiveLanguage(null);
    setQuery("");
  }, []);

  if (isLoading) return <CoursesSkeleton />;

  return (
    <div className="mx-auto flex min-h-full w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:gap-8 md:px-10 md:py-10">
      <CourseFilters
        totalCount={courseList.length}
        filteredCount={filteredCourses.length}
        languages={languageFacets}
        activeLanguage={activeLanguage}
        onLanguageChange={setActiveLanguage}
        query={query}
        onQueryChange={setQuery}
        isInstructor={isInstructor}
        onCreate={handleCreate}
        onJoin={handleJoin}
      />

      {isInstructor && CANVAS_ENABLED ? <CanvasCoursePicker /> : null}

      {courseList.length === 0 ? (
        <EmptyHive
          isInstructor={isInstructor}
          onCreate={handleCreate}
          onJoin={handleJoin}
        />
      ) : filteredCourses.length === 0 ? (
        <EmptyFiltered onClear={resetFilters} />
      ) : (
        <ul
          className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"
          aria-label="Course list"
        >
          {filteredCourses.map((course) => (
            <li key={course.id}>
              <CourseRowCard
                course={course}
                className="h-full"
                href={
                  isInstructor
                    ? `/teacher/courses/${course.id}`
                    : undefined
                }
              />
            </li>
          ))}
        </ul>
      )}

      <CreateCourseDialog open={createOpen} onOpenChange={setCreateOpen} />
      <JoinCourseDialog open={joinOpen} onOpenChange={setJoinOpen} />
    </div>
  );
}

function CoursesSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:px-10 md:py-10">
      <Skeleton className="h-12 w-40" />
      <Skeleton className="h-9 w-80" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-32 rounded-[var(--radius-2xl)]" />
        ))}
      </div>
    </div>
  );
}

interface EmptyHiveProps {
  readonly isInstructor: boolean;
  readonly onCreate: () => void;
  readonly onJoin: () => void;
}

function EmptyHive({ isInstructor, onCreate, onJoin }: EmptyHiveProps) {
  return (
    <div className="flex flex-col items-center rounded-[var(--radius-2xl)] border border-dashed border-[var(--color-border-hover)] bg-[var(--color-surface-hover)] px-6 py-16 text-center">
      <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-[var(--color-primary-light)]">
        <BookOpen className="size-6 text-[var(--color-primary)]" />
      </div>
      <h2 className="mt-4 text-xl font-semibold text-[var(--color-text)]">
        No courses yet
      </h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-[var(--color-text-secondary)]">
        {isInstructor
          ? "Create your first course to start uploading materials and generating quizzes."
          : "Ask your instructor for the 8-character enrollment code to join your first course."}
      </p>
      <Button className="mt-6 gap-2" onClick={isInstructor ? onCreate : onJoin}>
        {isInstructor ? (
          <>
            <Plus className="size-4" /> Create your first course
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

function EmptyFiltered({ onClear }: { onClear: () => void }) {
  return (
    <div className="flex flex-col items-center rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface-hover)] px-6 py-12 text-center">
      <p className="text-sm font-semibold text-[var(--color-text)]">
        No courses match these filters.
      </p>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
        Try clearing the language filter or search.
      </p>
      <button
        type="button"
        onClick={onClear}
        className="mt-4 rounded-[var(--radius-pill)] bg-[var(--color-text)] px-4 py-1.5 text-xs font-semibold text-[var(--color-surface)]"
      >
        Reset filters
      </button>
    </div>
  );
}
