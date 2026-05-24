"use client";

import { Suspense, use } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRole } from "@/hooks/use-role";
import {
  BookOpen,
  Calendar,
  FileText,
  Clock,
  Upload as UploadIcon,
  Sparkles,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { UploadZone } from "@/components/documents/upload-zone";
import { QuizList } from "@/components/quiz/quiz-list";
import { FlashcardList } from "@/components/flashcard/flashcard-list";
import { PronunciationList } from "@/components/pronunciation/pronunciation-list";
import { ProgressCard } from "@/components/gamification/progress-card";
import { Leaderboard } from "@/components/gamification/leaderboard";
import { BadgeDisplay } from "@/components/gamification/badge-display";
import { SummaryCard } from "@/components/summary/summary-card";
import { EnrollCodeCard } from "@/components/course/enroll-code-card";
import { CourseDescriptionCard } from "@/components/course/course-description-card";
import { CanvasTab } from "@/components/canvas/canvas-tab";
import { CANVAS_ENABLED } from "@/lib/features";
import { CourseAnalytics } from "@/components/analytics/course-analytics";
import { LiveSessionsPanel } from "@/components/live-quiz/live-sessions-panel";
import { SyllabusUploadCard } from "@/components/documents/syllabus-upload-card";
import { useCourse } from "@/hooks/use-courses";
import { useDocuments, useDeleteDocument, type DocumentResponse } from "@/hooks/use-documents";
import { useProgress } from "@/hooks/use-progress";
import {
  formatFileSize,
  formatRelativeTime,
  getFileTypeLabel,
} from "@/lib/format";

type DocumentStatus = "pending" | "processing" | "ready" | "failed";

const KNOWN_DOCUMENT_STATUSES: readonly DocumentStatus[] = [
  "pending",
  "processing",
  "ready",
  "failed",
];

function toDocumentStatus(status: string): DocumentStatus {
  return (KNOWN_DOCUMENT_STATUSES as readonly string[]).includes(status)
    ? (status as DocumentStatus)
    : "pending";
}

function statusBadgeClasses(status: DocumentStatus): string {
  switch (status) {
    case "ready":
      return "bg-[var(--color-success-light)] text-[var(--color-success)] border-transparent";
    case "processing":
      return "bg-[var(--color-primary-light)] text-[var(--color-primary)] border-transparent";
    case "pending":
      return "bg-[var(--color-warning-light)] text-[var(--color-warning)] border-transparent";
    case "failed":
      return "bg-[var(--color-error-light)] text-[var(--color-error)] border-transparent";
  }
}

function statusLabel(status: DocumentStatus): string {
  switch (status) {
    case "ready":
      return "Ready";
    case "processing":
      return "Processing";
    case "pending":
      return "Pending";
    case "failed":
      return "Failed";
  }
}

const ALLOWED_TABS_STUDENT = [
  "overview",
  "materials",
  "quizzes",
  "flashcards",
  "revision",
  "pronunciation",
  "live",
  "progress",
  "leaderboard",
] as const;
const ALLOWED_TABS_INSTRUCTOR = [
  ...ALLOWED_TABS_STUDENT,
  "students",
  ...(CANVAS_ENABLED ? (["canvas"] as const) : []),
] as const;
type AllowedTab =
  | (typeof ALLOWED_TABS_STUDENT)[number]
  | (typeof ALLOWED_TABS_INSTRUCTOR)[number];

function resolveActiveTab(raw: string | null, isInstructor: boolean): AllowedTab {
  const allowed = (
    isInstructor ? ALLOWED_TABS_INSTRUCTOR : ALLOWED_TABS_STUDENT
  ) as readonly string[];
  if (raw && allowed.includes(raw)) {
    return raw as AllowedTab;
  }
  return "overview";
}

interface CourseDetailPageProps {
  params: Promise<{ courseId: string }>;
}

export default function CourseDetailPage({ params }: CourseDetailPageProps) {
  return (
    <Suspense fallback={<CourseDetailSkeleton />}>
      <CourseDetailResolver params={params} />
    </Suspense>
  );
}

function CourseDetailResolver({ params }: CourseDetailPageProps) {
  const { courseId } = use(params);
  return (
    <Suspense fallback={<CourseDetailSkeleton />}>
      <CourseDetailContent courseId={courseId} />
    </Suspense>
  );
}

function CourseDetailSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-[var(--radius-lg)]" />
        ))}
      </div>
    </div>
  );
}

function CourseDetailContent({ courseId }: { courseId: string }) {
  const searchParams = useSearchParams();
  const { isInstructor, isLoaded: roleLoaded } = useRole();
  const activeTab = resolveActiveTab(searchParams.get("tab"), isInstructor);
  const { data: course, isLoading: courseLoading } = useCourse(courseId);
  const { data: documents, isLoading: docsLoading } = useDocuments(courseId);
  const deleteDocument = useDeleteDocument(courseId);
  const { data: progress, isLoading: progressLoading } = useProgress(courseId);

  const isLoaded = roleLoaded && !courseLoading;

  if (!isLoaded || !course) {
    return (
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-40" />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-[var(--radius-lg)]" />
          ))}
        </div>
      </div>
    );
  }

  const docList: readonly DocumentResponse[] = documents ?? [];
  const documentCount = docList.length;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* Course header */}
      <section>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-[var(--color-text)]">
                {course.name}
              </h1>
              <Badge variant="secondary">{course.language}</Badge>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-[var(--color-text-muted)]">
              {course.code && (
                <span className="flex items-center gap-1">
                  <BookOpen className="size-3.5" />
                  {course.code}
                </span>
              )}
              <span className="flex items-center gap-1">
                <Calendar className="size-3.5" />
                {course.semester ?? "No semester"}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Tab content — navigation is in the sidebar */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* Stats cards */}
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <CardContent className="flex items-center gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                  <FileText className="size-5" />
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Documents
                  </p>
                  {docsLoading ? (
                    <Skeleton className="h-7 w-8" />
                  ) : (
                    <p className="text-xl font-bold text-[var(--color-text)]">
                      {documentCount}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3">
                <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                  <Clock className="size-5" />
                </div>
                <div>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    Last Updated
                  </p>
                  <p className="text-sm font-medium text-[var(--color-text)]">
                    {formatRelativeTime(course.updated_at)}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Description */}
          <CourseDescriptionCard
            courseId={courseId}
            description={course.description}
            canEdit={isInstructor}
          />

          {/* Enrollment code — instructors only */}
          {isInstructor && <EnrollCodeCard enrollCode={course.enroll_code} />}

          {/* AI Summary */}
          <SummaryCard courseId={courseId} isInstructor={isInstructor} />
        </div>
      )}

      {activeTab === "materials" && (
        <div className="space-y-6">
          {isInstructor && (
            <>
              <SyllabusUploadCard courseId={courseId} />
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <UploadIcon className="size-4" />
                    Upload Materials
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <UploadZone courseId={courseId} />
                </CardContent>
              </Card>
            </>
          )}

          {/* Document list */}
          <Card>
            <CardHeader>
              <CardTitle>
                Documents ({docsLoading ? "..." : documentCount})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {docsLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3 py-3">
                      <Skeleton className="size-5" />
                      <div className="flex-1 space-y-2">
                        <Skeleton className="h-4 w-48" />
                        <Skeleton className="h-3 w-32" />
                      </div>
                      <Skeleton className="h-5 w-16 rounded-full" />
                    </div>
                  ))}
                </div>
              ) : docList.length > 0 ? (
                <ul className="divide-y divide-[var(--color-border)]">
                  {docList.map((doc) => (
                    <li
                      key={doc.id}
                      className="flex items-center gap-3 py-3 first:pt-0 last:pb-0"
                    >
                      <FileText className="size-5 shrink-0 text-[var(--color-text-muted)]" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-[var(--color-text)]">
                          {doc.filename}
                        </p>
                        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                          <span>{getFileTypeLabel(doc.filename)}</span>
                          <Separator
                            orientation="vertical"
                            className="h-3"
                          />
                          <span>{formatFileSize(doc.file_size)}</span>
                          <Separator
                            orientation="vertical"
                            className="h-3"
                          />
                          <span className="flex items-center gap-1">
                            <Clock className="size-3" />
                            {formatRelativeTime(doc.created_at)}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          className={statusBadgeClasses(
                            toDocumentStatus(doc.status)
                          )}
                        >
                          {statusLabel(toDocumentStatus(doc.status))}
                        </Badge>
                        {isInstructor && (
                          <button
                            onClick={() => deleteDocument.mutate(doc.id)}
                            disabled={deleteDocument.isPending}
                            className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-muted)] transition-colors duration-[var(--duration-fast)] hover:bg-[oklch(93%_0.05_25)] hover:text-[var(--color-error)]"
                            aria-label={`Delete ${doc.filename}`}
                          >
                            <Trash2 className="size-4" />
                          </button>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="flex flex-col items-center py-8 text-center">
                  <FileText className="mb-2 size-8 text-[var(--color-text-muted)]" />
                  <p className="text-sm text-[var(--color-text-muted)]">
                    No documents uploaded yet
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "quizzes" && (
        <div className="pt-0">
          <QuizList courseId={courseId} isInstructor={isInstructor} />
        </div>
      )}

      {activeTab === "flashcards" && (
        <div>
          <FlashcardList courseId={courseId} isInstructor={isInstructor} />
        </div>
      )}

      {activeTab === "revision" && (
        <div className="space-y-4">
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-8">
              <div className="flex size-12 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[var(--color-primary)]">
                <Sparkles className="size-6" />
              </div>
              <div className="text-center">
                <h3 className="text-lg font-semibold text-[var(--color-text)]">Adaptive Revision</h3>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                  Practice with AI-generated questions that adapt to your level
                </p>
              </div>
              <Link href={`/dashboard/courses/${courseId}/revision`}>
                <Button>Start Revision</Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "pronunciation" && (
        <div>
          <PronunciationList courseId={courseId} isInstructor={isInstructor} />
        </div>
      )}

      {activeTab === "live" && (
        <LiveSessionsPanel courseId={courseId} />
      )}

      {activeTab === "progress" && (
        <div className="space-y-6">
          <ProgressCard progress={progress} isLoading={progressLoading} />
          <BadgeDisplay badges={progress?.badges ?? []} />
        </div>
      )}

      {activeTab === "leaderboard" && (
        <div>
          <Leaderboard courseId={courseId} />
        </div>
      )}

      {activeTab === "students" && (
        <CourseAnalytics courseId={courseId} />
      )}

      {CANVAS_ENABLED && activeTab === "canvas" && isInstructor && (
        <CanvasTab meliCourseId={courseId} />
      )}

    </div>
  );
}

