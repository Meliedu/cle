"use client";

import { CheckCircle, XCircle } from "lucide-react";

interface ItemFeedbackProps {
  readonly score: number;
  readonly isCorrect?: boolean | null;
  readonly correctAnswer?: string | null;
  readonly explanation?: string | null;
}

export function ItemFeedback({
  score,
  isCorrect,
  correctAnswer,
  explanation,
}: ItemFeedbackProps) {
  const isPositive = isCorrect === true || (isCorrect == null && score >= 3);

  return (
    <div
      data-testid="item-feedback"
      className="rounded-[var(--radius-lg)] border p-4"
      style={{
        borderColor: isPositive
          ? "var(--color-success)"
          : "var(--color-error)",
        backgroundColor: isPositive
          ? "var(--color-success-light)"
          : "var(--color-error-light)",
      }}
    >
      <div className="flex items-start gap-3">
        {isPositive ? (
          <CheckCircle
            className="mt-0.5 size-5 shrink-0"
            style={{ color: "var(--color-success)" }}
          />
        ) : (
          <XCircle
            className="mt-0.5 size-5 shrink-0"
            style={{ color: "var(--color-error)" }}
          />
        )}

        <div className="min-w-0 flex-1 space-y-1">
          <p
            className="text-sm font-semibold"
            style={{
              color: isPositive
                ? "var(--color-success)"
                : "var(--color-error)",
            }}
          >
            {isPositive ? "Correct!" : "Incorrect"}
            <span className="ml-2 font-normal text-[var(--color-text-muted)]">
              Score: {score}
            </span>
          </p>

          {correctAnswer != null && !isPositive && (
            <p className="text-sm text-[var(--color-text)]">
              <span className="font-medium">Correct answer:</span>{" "}
              {correctAnswer}
            </p>
          )}

          {explanation != null && (
            <p className="text-sm leading-relaxed text-[var(--color-text-secondary)]">
              {explanation}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
