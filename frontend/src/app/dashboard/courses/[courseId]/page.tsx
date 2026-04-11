"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useRole } from "@/hooks/use-role";
import {
  BookOpen,
  Users,
  Calendar,
  FileText,
  Clock,
  Upload as UploadIcon,
  Sparkles,
  Mic,
  Radio,
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
import { ProgressCard } from "@/components/gamification/progress-card";
import { Leaderboard } from "@/components/gamification/leaderboard";
import { BadgeDisplay } from "@/components/gamification/badge-display";
import { GenerateSummaryDialog } from "@/components/summary/generate-summary-dialog";
import { CourseAnalytics } from "@/components/analytics/course-analytics";
import { RecalibrationOverview } from "@/components/recalibration/overview";
import { useCourse } from "@/hooks/use-courses";
import { useDocuments, useDeleteDocument, type DocumentResponse } from "@/hooks/use-documents";
import { useProgress } from "@/hooks/use-progress";
import {
  formatFileSize,
  formatRelativeTime,
  getFileTypeLabel,
} from "@/lib/format";

type DocumentStatus = "pending" | "processing" | "ready" | "failed";

function statusBadgeClasses(status: DocumentStatus): string {
  switch (status) {
    case "ready":
      return "bg-[oklch(90%_0.05_145)] text-[var(--color-success)] border-transparent";
    case "processing":
      return "bg-[oklch(90%_0.05_260)] text-[var(--color-primary)] border-transparent";
    case "pending":
      return "bg-[oklch(93%_0.05_75)] text-[var(--color-warning)] border-transparent";
    case "failed":
      return "bg-[oklch(93%_0.05_25)] text-[var(--color-error)] border-transparent";
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

interface CourseDetailPageProps {
  params: Promise<{ courseId: string }>;
}

export default function CourseDetailPage({ params }: CourseDetailPageProps) {
  const { courseId } = use(params);
  const searchParams = useSearchParams();
  const activeTab = searchParams.get("tab") || "overview";
  const { isInstructor, isLoaded: roleLoaded } = useRole();
  const { data: course, isLoading: courseLoading } = useCourse(courseId);
  const { data: documents, isLoading: docsLoading } = useDocuments(courseId);
  const deleteDocument = useDeleteDocument(courseId);
  const { data: progress, isLoading: progressLoading } = useProgress(courseId);
  const [summaryDialogOpen, setSummaryDialogOpen] = useState(false);

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
          <Card>
            <CardHeader>
              <CardTitle>About this course</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="leading-relaxed text-[var(--color-text-secondary)]">
                {course.description ?? "No description provided."}
              </p>
            </CardContent>
          </Card>

          {/* AI Summary */}
          <Card>
            <CardContent className="flex items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-medium text-[var(--color-text)]">
                  AI Course Summary
                </h3>
                <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                  Generate an overview of all uploaded course materials.
                </p>
              </div>
              {isInstructor ? (
                <Button variant="outline" onClick={() => setSummaryDialogOpen(true)}>
                  <Sparkles className="size-4" />
                  Generate Summary
                </Button>
              ) : (
                <p className="text-xs text-[var(--color-text-muted)]">
                  AI summaries are generated by your instructor.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "materials" && (
        <div className="space-y-6">
          {isInstructor && (
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
                            doc.status as DocumentStatus
                          )}
                        >
                          {statusLabel(doc.status as DocumentStatus)}
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
          <Card>
            <CardContent className="flex flex-col items-center py-12 text-center">
              <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-success-light)]">
                <Mic className="size-6 text-[var(--color-success)]" />
              </div>
              <h3 className="font-semibold text-[var(--color-text)]">
                Pronunciation Practice
              </h3>
              <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                Practice your pronunciation and get AI-powered feedback on accuracy, fluency, and completeness.
              </p>
              <Link href={`/dashboard/courses/${courseId}/pronunciation`}>
                <Button className="mt-4">
                  <Mic className="size-4" />
                  Start Practice
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === "live" && (
        <div>
          <Card>
            <CardContent className="flex flex-col items-center py-12 text-center">
              <div className="mb-4 flex size-12 items-center justify-center rounded-full bg-[var(--color-success-light)]">
                <Radio className="size-6 text-[var(--color-success)]" />
              </div>
              <h3 className="font-semibold text-[var(--color-text)]">
                Live Quiz Sessions
              </h3>
              <p className="mt-1 max-w-sm text-sm text-[var(--color-text-muted)]">
                {isInstructor
                  ? "Host real-time quiz sessions and engage your students with live competition."
                  : "Join live quiz sessions hosted by your instructor."}
              </p>
              <Link href={`/dashboard/courses/${courseId}/live`}>
                <Button className="mt-4">
                  <Radio className="size-4" />
                  {isInstructor ? "Manage Live Sessions" : "Join Live Session"}
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
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

      {activeTab === "recalibration" && isInstructor && (
        <RecalibrationOverview courseId={courseId} />
      )}

      <GenerateSummaryDialog
        courseId={courseId}
        open={summaryDialogOpen}
        onOpenChange={setSummaryDialogOpen}
      />
    </div>
  );
}

