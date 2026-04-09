"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Check } from "lucide-react";

interface FlashcardItemProps {
  readonly item: {
    readonly front: string;
    readonly back: string;
  };
  readonly onAnswer: (params: {
    quality: number;
    time_taken_ms: number;
  }) => void;
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

export function FlashcardItem({ item, onAnswer }: FlashcardItemProps) {
  const [isFlipped, setIsFlipped] = useState(false);
  const [hasRated, setHasRated] = useState(false);
  const mountTimeRef = useRef<number>(Date.now());

  // Reset state when item changes
  useEffect(() => {
    setIsFlipped(false);
    setHasRated(false);
    mountTimeRef.current = Date.now();
  }, [item.front, item.back]);

  const handleFlip = useCallback(() => {
    if (!hasRated) {
      setIsFlipped((prev) => !prev);
    }
  }, [hasRated]);

  const handleRate = useCallback(
    (quality: RatingQuality) => {
      if (hasRated) return;

      setHasRated(true);
      const elapsed = Date.now() - mountTimeRef.current;
      onAnswer({ quality, time_taken_ms: elapsed });
    },
    [hasRated, onAnswer]
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

  return (
    <div className="space-y-6">
      {/* Flip card */}
      <div
        className="perspective-[1000px] cursor-pointer"
        onClick={handleFlip}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label={
          isFlipped
            ? "Card back is shown. Click to flip."
            : "Click to reveal answer."
        }
      >
        <div
          className="relative h-[320px] w-full transition-transform duration-[450ms] ease-[cubic-bezier(0.16,1,0.3,1)]"
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
              {item.front}
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
              {item.back}
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
