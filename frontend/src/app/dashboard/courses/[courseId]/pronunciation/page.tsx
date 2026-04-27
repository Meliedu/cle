"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Languages, Mic } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { useRole } from "@/hooks/use-role";
import { useCourse } from "@/hooks/use-courses";
import { PronunciationList } from "@/components/pronunciation/pronunciation-list";

interface PronunciationPageProps {
  params: Promise<{ courseId: string }>;
}

export default function PronunciationPage({ params }: PronunciationPageProps) {
  const { courseId } = use(params);
  const { isInstructor, isLoaded } = useRole();
  const { data: course, isLoading: courseLoading } = useCourse(courseId);

  if (!isLoaded || courseLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="space-y-1">
        <Link
          href={`/dashboard/courses/${courseId}`}
          className="mb-2 inline-flex items-center gap-1 text-sm transition-colors duration-[var(--duration-fast)]"
          style={{ color: "var(--color-text-muted)" }}
        >
          <ArrowLeft className="size-3.5" />
          Back to course
        </Link>
        <div className="flex items-center gap-3">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)]"
            style={{
              backgroundColor: "var(--color-success-light)",
              color: "var(--color-success)",
            }}
          >
            <Mic className="size-5" />
          </div>
          <div>
            <h1
              className="text-xl font-bold"
              style={{ color: "var(--color-text)" }}
            >
              Pronunciation
            </h1>
            {course && (
              <p
                className="flex items-center gap-1.5 text-sm"
                style={{ color: "var(--color-text-muted)" }}
              >
                <Languages className="size-3.5" />
                {course.name} — {course.language}
              </p>
            )}
          </div>
        </div>
      </section>

      <PronunciationList courseId={courseId} isInstructor={isInstructor} />
    </div>
  );
}
