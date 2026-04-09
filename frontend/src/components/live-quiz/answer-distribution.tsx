"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart3 } from "lucide-react";

const OPTION_COLORS: Record<string, string> = {
  A: "var(--color-primary)",
  B: "var(--color-accent)",
  C: "var(--color-success)",
  D: "var(--color-warning)",
};

interface AnswerDistributionProps {
  readonly distribution: Record<string, number>;
  readonly correctAnswer?: string;
  readonly totalAnswers: number;
}

export function AnswerDistribution({
  distribution,
  correctAnswer,
  totalAnswers,
}: AnswerDistributionProps) {
  const maxCount = Math.max(...Object.values(distribution), 1);
  const options = ["A", "B", "C", "D"];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <BarChart3 className="size-4" />
          Answer Distribution
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {options.map((option) => {
          const count = distribution[option] ?? 0;
          const percentage = totalAnswers > 0 ? (count / totalAnswers) * 100 : 0;
          const widthPercent = maxCount > 0 ? (count / maxCount) * 100 : 0;
          const isCorrect = correctAnswer === option;
          const barColor = OPTION_COLORS[option] ?? "var(--color-text-muted)";

          return (
            <div key={option} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span
                  className={`font-medium ${
                    isCorrect
                      ? "text-[var(--color-success)]"
                      : "text-[var(--color-text)]"
                  }`}
                >
                  {option}
                  {isCorrect && " (correct)"}
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  {count} ({percentage.toFixed(0)}%)
                </span>
              </div>
              <div className="h-6 overflow-hidden rounded-[var(--radius-sm)] bg-[var(--color-surface-hover)]">
                <div
                  className="h-full rounded-[var(--radius-sm)] transition-all duration-[var(--duration-slow)]"
                  style={{
                    width: `${widthPercent}%`,
                    backgroundColor: barColor,
                    opacity: isCorrect ? 1 : 0.6,
                  }}
                />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
