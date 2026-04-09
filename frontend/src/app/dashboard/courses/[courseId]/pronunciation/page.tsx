"use client";

import { use, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Mic, Languages } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Recorder } from "@/components/pronunciation/recorder";
import { ScoreDisplay } from "@/components/pronunciation/score-display";
import { HistoryChart } from "@/components/pronunciation/history-chart";
import { useCourse } from "@/hooks/use-courses";
import {
  usePronunciationGrade,
  type PronunciationGradeResponse,
} from "@/hooks/use-pronunciation";

interface PronunciationPageProps {
  params: Promise<{ courseId: string }>;
}

export default function PronunciationPage({ params }: PronunciationPageProps) {
  const { courseId } = use(params);
  const queryClient = useQueryClient();
  const { data: course, isLoading: courseLoading } = useCourse(courseId);
  const gradeMutation = usePronunciationGrade();

  const [referenceText, setReferenceText] = useState("");
  const [lastResult, setLastResult] = useState<PronunciationGradeResponse | null>(
    null
  );

  const language = course?.language ?? "english";

  const handleRecordingComplete = useCallback(
    async (audioBlob: Blob) => {
      if (!referenceText.trim()) return;

      try {
        const result = await gradeMutation.mutateAsync({
          audioBlob,
          referenceText: referenceText.trim(),
          courseId,
          language,
        });
        setLastResult(result);
        // Invalidate history so it refreshes with the new entry
        queryClient.invalidateQueries({
          queryKey: ["pronunciation-history", courseId],
        });
      } catch {
        // Error is available via gradeMutation.error
      }
    },
    [referenceText, courseId, language, gradeMutation, queryClient]
  );

  if (courseLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
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
              Pronunciation Practice
            </h1>
            {course && (
              <p
                className="flex items-center gap-1.5 text-sm"
                style={{ color: "var(--color-text-muted)" }}
              >
                <Languages className="size-3.5" />
                {course.name} — {language}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Reference text input */}
      <Card>
        <CardHeader>
          <CardTitle>Reference Text</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p
            className="text-sm"
            style={{ color: "var(--color-text-muted)" }}
          >
            Enter the text you want to practice. Then record yourself reading
            it aloud.
          </p>
          <textarea
            value={referenceText}
            onChange={(e) => setReferenceText(e.target.value)}
            placeholder="Type or paste the text you want to practice..."
            rows={3}
            className="w-full resize-none rounded-[var(--radius-md)] border px-3 py-2 text-sm transition-colors duration-[var(--duration-fast)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-2"
            style={{
              borderColor: "var(--color-border)",
              backgroundColor: "var(--color-surface)",
              color: "var(--color-text)",
              // focus ring color set via focus: classes
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = "var(--color-primary)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = "var(--color-border)";
            }}
          />
        </CardContent>
      </Card>

      {/* Recorder */}
      <Recorder
        onRecordingComplete={handleRecordingComplete}
        isProcessing={gradeMutation.isPending}
      />

      {/* Validation: must have text to record */}
      {!referenceText.trim() && !gradeMutation.isPending && (
        <p
          className="text-center text-sm"
          style={{ color: "var(--color-text-muted)" }}
        >
          Please enter reference text above before recording.
        </p>
      )}

      {/* Error from grading */}
      {gradeMutation.error && (
        <Card>
          <CardContent className="py-4">
            <p
              className="text-center text-sm"
              style={{ color: "var(--color-error)" }}
            >
              {gradeMutation.error instanceof Error
                ? gradeMutation.error.message
                : "Pronunciation grading failed. Please try again."}
            </p>
            <div className="mt-3 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => gradeMutation.reset()}
              >
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Score display */}
      <ScoreDisplay result={lastResult} />

      {/* History */}
      <HistoryChart courseId={courseId} />
    </div>
  );
}
