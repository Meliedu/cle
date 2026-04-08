"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft,
  RotateCcw,
  ChevronRight,
  Check,
  Trophy,
} from "lucide-react";
import { apiFetch } from "@/lib/api";

interface Flashcard {
  readonly id: string;
  readonly front: string;
  readonly back: string;
}

interface FlashcardSetDetail {
  readonly id: string;
  readonly title: string;
  readonly cards: readonly Flashcard[];
}

interface FlashcardPlayerProps {
  readonly setId: string;
  readonly courseId: string;
}

type RatingQuality = 0 | 2 | 4 | 5;

interface RatingOption {
  readonly label: string;
  readonly quality: RatingQuality;
  readonly className: string;
}

const ratingOptions: readonly RatingOption[] = [
  {
    label: "Again",
    quality: 0,
    className:
      "border-[oklch(80%_0.12_25)] bg-[oklch(96%_0.03_25)] text-[var(--color-error)] hover:bg-[oklch(93%_0.05_25)] focus-visible:ring-[oklch(55%_0.22_25/0.3)]",
  },
  {
    label: "Hard",
    quality: 2,
    className:
      "border-[oklch(85%_0.1_75)] bg-[oklch(97%_0.02_75)] text-[oklch(45%_0.12_75)] hover:bg-[oklch(94%_0.04_75)] focus-visible:ring-[oklch(70%_0.17_75/0.3)]",
  },
  {
    label: "Good",
    quality: 4,
    className:
      "border-[oklch(85%_0.1_260)] bg-[var(--color-primary-light)] text-[var(--color-primary)] hover:bg-[oklch(92%_0.05_260)] focus-visible:ring-[oklch(55%_0.2_260/0.3)]",
  },
  {
    label: "Easy",
    quality: 5,
    className:
      "border-[oklch(80%_0.1_145)] bg-[oklch(96%_0.03_145)] text-[var(--color-success)] hover:bg-[oklch(93%_0.05_145)] focus-visible:ring-[oklch(55%_0.18_145/0.3)]",
  },
] as const;

function PlayerSkeleton() {
  return (
    <div className="mx-auto max-w-[600px] space-y-6">
      <div className="flex items-center gap-3">
        <Skeleton className="size-8 rounded-lg" />
        <Skeleton className="h-5 w-48" />
      </div>
      <Skeleton className="h-2 w-full rounded-full" />
      <Skeleton className="h-[360px] w-full rounded-[var(--radius-xl)]" />
      <div className="flex justify-center gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-20 rounded-lg" />
        ))}
      </div>
    </div>
  );
}

export function FlashcardPlayer({ setId, courseId }: FlashcardPlayerProps) {
  const { getToken, isSignedIn } = useAuth();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [hasRated, setHasRated] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [cardsStudied, setCardsStudied] = useState(0);

  const {
    data: flashcardSet,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["flashcard-set", setId],
    queryFn: async (): Promise<FlashcardSetDetail> => {
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");
      return apiFetch<FlashcardSetDetail>(`/flashcard-sets/${setId}`, {
        token: token!,
      });
    },
    enabled: isSignedIn === true,
    retry: (count, error) => {
      if (error.message.includes("401") || error.message.includes("Unauthorized")) return false;
      return count < 3;
    },
  });

  const totalCards = flashcardSet?.cards.length ?? 0;
  const currentCard = flashcardSet?.cards[currentIndex];
  const progressPercent =
    totalCards > 0 ? ((currentIndex + 1) / totalCards) * 100 : 0;

  const handleFlip = useCallback(() => {
    if (!hasRated) {
      setIsFlipped((prev) => !prev);
    }
  }, [hasRated]);

  const handleRate = useCallback(
    async (quality: RatingQuality) => {
      if (!currentCard) return;

      setHasRated(true);

      try {
        const token = await getToken();
        if (!token) throw new Error("Not authenticated");
        await apiFetch(`/flashcard-sets/${setId}/progress`, {
          method: "PUT",
          token: token!,
          body: JSON.stringify({
            card_id: currentCard.id,
            quality,
          }),
        });
      } catch {
        // Rating failure is non-blocking; the user can continue studying
      }

      const nextStudied = cardsStudied + 1;
      setCardsStudied(nextStudied);

      // Brief delay before advancing to next card
      setTimeout(() => {
        if (currentIndex + 1 >= totalCards) {
          setIsComplete(true);
        } else {
          setCurrentIndex((prev) => prev + 1);
          setIsFlipped(false);
          setHasRated(false);
        }
      }, 300);
    },
    [currentCard, currentIndex, totalCards, setId, getToken, cardsStudied]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        if (!isFlipped) {
          setIsFlipped(true);
        }
      }
    },
    [isFlipped]
  );

  if (isLoading) {
    return <PlayerSkeleton />;
  }

  if (error || !flashcardSet) {
    return (
      <div className="mx-auto max-w-[600px]">
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <p className="text-sm text-[var(--color-error)]">
              Failed to load flashcard set. Please try again.
            </p>
            <Link href={`/dashboard/courses/${courseId}`}>
              <Button variant="outline" className="mt-4">
                <ArrowLeft className="size-4" />
                Back to Course
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (totalCards === 0) {
    return (
      <div className="mx-auto max-w-[600px]">
        <Card>
          <CardContent className="flex flex-col items-center py-12 text-center">
            <p className="text-sm text-[var(--color-text-muted)]">
              This flashcard set has no cards.
            </p>
            <Link href={`/dashboard/courses/${courseId}`}>
              <Button variant="outline" className="mt-4">
                <ArrowLeft className="size-4" />
                Back to Course
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isComplete) {
    return (
      <div className="mx-auto max-w-[600px]">
        <Card>
          <CardContent className="flex flex-col items-center py-16 text-center">
            <div className="mb-6 flex size-16 items-center justify-center rounded-full bg-[oklch(96%_0.03_145)]">
              <Trophy className="size-8 text-[var(--color-success)]" />
            </div>
            <h2 className="text-2xl font-bold text-[var(--color-text)]">
              Session Complete!
            </h2>
            <p className="mt-2 text-sm text-[var(--color-text-muted)]">
              Cards studied: {cardsStudied}
            </p>
            <div className="mt-6 flex gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setCurrentIndex(0);
                  setIsFlipped(false);
                  setHasRated(false);
                  setIsComplete(false);
                  setCardsStudied(0);
                }}
              >
                <RotateCcw className="size-4" />
                Study Again
              </Button>
              <Link href={`/dashboard/courses/${courseId}`}>
                <Button>
                  Back to Course
                  <ChevronRight className="size-4" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[600px] space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link href={`/dashboard/courses/${courseId}`}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="size-4" />
          </Button>
        </Link>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-lg font-semibold text-[var(--color-text)]">
            {flashcardSet.title}
          </h2>
          <p className="text-xs text-[var(--color-text-muted)]">
            Card {currentIndex + 1} of {totalCards}
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-border)]">
        <div
          className="h-full rounded-full bg-[var(--color-primary)] transition-[width] duration-[var(--duration-normal)] ease-[var(--ease-out)]"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {/* Flashcard */}
      <div
        className="perspective-[1000px] cursor-pointer"
        onClick={handleFlip}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label={
          isFlipped ? "Card back is shown. Click to flip." : "Click to reveal answer."
        }
      >
        <div
          className="relative h-[360px] w-full transition-transform duration-[450ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            transformStyle: "preserve-3d",
            transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)",
          }}
        >
          {/* Front face */}
          <div
            className="absolute inset-0 flex items-center justify-center rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-8 shadow-[var(--shadow-lg)]"
            style={{ backfaceVisibility: "hidden" }}
          >
            <p className="text-center text-xl font-medium leading-relaxed text-[var(--color-text)]">
              {currentCard?.front}
            </p>
          </div>

          {/* Back face */}
          <div
            className="absolute inset-0 flex items-center justify-center rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-primary-light)] p-8 shadow-[var(--shadow-lg)]"
            style={{
              backfaceVisibility: "hidden",
              transform: "rotateY(180deg)",
            }}
          >
            <p className="text-center text-xl font-medium leading-relaxed text-[var(--color-text)]">
              {currentCard?.back}
            </p>
          </div>
        </div>
      </div>

      {/* Tap hint or rating buttons */}
      {!isFlipped ? (
        <p className="text-center text-sm text-[var(--color-text-muted)]">
          Tap the card to reveal the answer
        </p>
      ) : (
        <div className="flex justify-center gap-3">
          {ratingOptions.map((option) => (
            <button
              key={option.quality}
              type="button"
              disabled={hasRated}
              onClick={() => handleRate(option.quality)}
              className={`inline-flex h-10 items-center justify-center rounded-lg border px-4 text-sm font-medium transition-all duration-[var(--duration-fast)] outline-none focus-visible:ring-3 disabled:pointer-events-none disabled:opacity-50 ${option.className}`}
            >
              {option.quality === 4 && <Check className="mr-1.5 size-3.5" />}
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
