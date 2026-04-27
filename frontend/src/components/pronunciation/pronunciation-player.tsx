"use client";

import { useState, useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Languages,
  Mic,
  Volume2,
} from "lucide-react";
import { DifficultyBadge } from "@/components/ui/difficulty-badge";
import { Recorder } from "./recorder";
import { ScoreDisplay } from "./score-display";
import {
  usePronunciationSet,
  type PronunciationItemResponse,
} from "@/hooks/use-pronunciation-sets";
import {
  usePronunciationGrade,
  type PronunciationGradeResponse,
} from "@/hooks/use-pronunciation";

interface PronunciationPlayerProps {
  readonly setId: string;
  readonly courseId: string;
}

// BCP-47 hints for SpeechSynthesis. Falls back to undefined (let the browser
// pick) when the language string isn't a known short code.
const LANG_TAGS: Record<string, string> = {
  english: "en-US",
  chinese: "zh-CN",
  mandarin: "zh-CN",
  cantonese: "zh-HK",
  spanish: "es-ES",
  french: "fr-FR",
  german: "de-DE",
  japanese: "ja-JP",
  korean: "ko-KR",
};

function speak(text: string, language: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  // Cancel any in-flight utterance so rapid taps don't queue up.
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const tag = LANG_TAGS[language.toLowerCase()];
  if (tag) u.lang = tag;
  window.speechSynthesis.speak(u);
}

export function PronunciationPlayer({
  setId,
  courseId,
}: PronunciationPlayerProps) {
  const queryClient = useQueryClient();
  const { data: pronSet, isLoading, error } = usePronunciationSet(setId);
  const gradeMutation = usePronunciationGrade();
  const [index, setIndex] = useState(0);
  const [scoresByItem, setScoresByItem] = useState<
    Record<string, PronunciationGradeResponse>
  >({});

  const items = useMemo(
    () => (pronSet ? [...pronSet.items].sort((a, b) => a.item_index - b.item_index) : []),
    [pronSet]
  );
  const current: PronunciationItemResponse | undefined = items[index];

  const handleRecordingComplete = useCallback(
    async (audioBlob: Blob) => {
      if (!current || !pronSet) return;
      try {
        const result = await gradeMutation.mutateAsync({
          audioBlob,
          referenceText: current.text,
          courseId,
          language: pronSet.language,
        });
        setScoresByItem((prev) => ({ ...prev, [current.id]: result }));
        queryClient.invalidateQueries({
          queryKey: ["pronunciation-history", courseId],
        });
      } catch {
        // surfaced via gradeMutation.error
      }
    },
    [current, pronSet, courseId, gradeMutation, queryClient]
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 rounded-[var(--radius-lg)]" />
        <Skeleton className="h-48 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (error || !pronSet) {
    return (
      <Card className="mx-auto max-w-3xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error
              ? error.message
              : "Failed to load pronunciation set"}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (items.length === 0) {
    return (
      <Card className="mx-auto max-w-3xl">
        <CardContent className="flex flex-col items-center py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            This set has no items yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!current) return null;
  const lastResult = scoresByItem[current.id] ?? null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Link
              href={`/dashboard/courses/${courseId}/pronunciation`}
              className="inline-flex"
            >
              <Button variant="ghost" size="sm">
                <ArrowLeft className="size-4" />
              </Button>
            </Link>
            <h1 className="text-xl font-bold text-[var(--color-text)]">
              {pronSet.title}
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2 pl-9">
            <Badge variant="outline">
              <Mic className="size-3" />
              Item {index + 1} of {items.length}
            </Badge>
            <Badge variant="outline">
              <Languages className="size-3" />
              {pronSet.language}
            </Badge>
          </div>
        </div>
      </div>

      <Separator />

      {/* Current item */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="capitalize">
              {current.item_type}
            </Badge>
            <DifficultyBadge value={current.difficulty} size="sm" />
          </div>
          <p className="text-3xl font-semibold leading-tight text-[var(--color-text)]">
            {current.text}
          </p>
          {current.phonetic && (
            <p className="font-mono text-base text-[var(--color-text-muted)]">
              {current.phonetic}
            </p>
          )}
          {current.translation && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                Translation
              </p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {current.translation}
              </p>
            </div>
          )}
          {current.tips && (
            <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                Tip
              </p>
              <p className="text-sm text-[var(--color-text)]">{current.tips}</p>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => speak(current.text, pronSet.language)}
            >
              <Volume2 className="size-4" />
              Listen
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Recorder */}
      <Recorder
        onRecordingComplete={handleRecordingComplete}
        isProcessing={gradeMutation.isPending}
      />

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

      <ScoreDisplay result={lastResult} />

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            gradeMutation.reset();
            setIndex((i) => Math.max(0, i - 1));
          }}
          disabled={index === 0}
        >
          <ChevronLeft className="size-4" />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            gradeMutation.reset();
            setIndex((i) => Math.min(items.length - 1, i + 1));
          }}
          disabled={index >= items.length - 1}
        >
          Next
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
