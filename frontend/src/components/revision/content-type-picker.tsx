"use client";

import { useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Brain, Layers, Mic } from "lucide-react";

type ContentType = "quiz" | "flashcard" | "speaking";

interface ContentTypePickerProps {
  readonly onSelect: (contentType: ContentType) => void;
}

interface ContentOption {
  readonly type: ContentType;
  readonly icon: typeof Brain;
  readonly title: string;
  readonly description: string;
  readonly accentHue: string;
}

const contentOptions: readonly ContentOption[] = [
  {
    type: "quiz",
    icon: Brain,
    title: "Quiz",
    description: "Multiple-choice questions to test your knowledge",
    accentHue: "80",
  },
  {
    type: "flashcard",
    icon: Layers,
    title: "Flashcard",
    description: "Flip cards with spaced-repetition rating",
    accentHue: "230",
  },
  {
    type: "speaking",
    icon: Mic,
    title: "Speaking",
    description: "Practice pronunciation with target phrases",
    accentHue: "155",
  },
] as const;

export function ContentTypePicker({ onSelect }: ContentTypePickerProps) {
  const handleSelect = useCallback(
    (type: ContentType) => () => {
      onSelect(type);
    },
    [onSelect]
  );

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="text-center">
        <h2 className="text-[var(--text-2xl)] font-bold text-[var(--color-text)]">
          Choose Your Practice
        </h2>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">
          Select a content type to start your revision session
        </p>
      </div>

      <div className="grid gap-4">
        {contentOptions.map((option) => {
          const Icon = option.icon;

          return (
            <Card
              key={option.type}
              className="cursor-pointer border-[var(--color-border)] bg-[var(--color-surface)] transition-all duration-[var(--duration-normal)] hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]"
              style={{ transitionTimingFunction: "var(--ease-out)" }}
              onClick={handleSelect(option.type)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect(option.type);
                }
              }}
              aria-label={`Start ${option.title} practice`}
            >
              <CardContent className="flex items-center gap-4 py-2">
                <div
                  className="flex size-12 shrink-0 items-center justify-center rounded-[var(--radius-lg)]"
                  style={{
                    backgroundColor: `oklch(95% 0.04 ${option.accentHue})`,
                  }}
                >
                  <Icon
                    className="size-6"
                    style={{
                      color: `oklch(55% 0.18 ${option.accentHue})`,
                    }}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-[var(--color-text)]">
                    {option.title}
                  </h3>
                  <p className="text-sm text-[var(--color-text-muted)]">
                    {option.description}
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
