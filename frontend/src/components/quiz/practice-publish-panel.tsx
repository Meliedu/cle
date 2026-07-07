"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Info, Loader2, Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import { useQuiz, usePublishQuiz } from "@/hooks/use-quizzes";

interface PracticePublishPanelProps {
  readonly courseId: string;
  readonly quizId: string;
}

/**
 * T063 — practice publish settings. Practice quizzes SKIP the score-policy gate
 * (Decision 7): `usePublishQuiz` publishes them freely and writes a
 * non-required `practice` work_item (Decision 8) so they never get auto-missed.
 * The panel surfaces a readiness summary + a note that practice needs no score
 * category, then publishes / re-publishes. Designed disabled + published states.
 */
export function PracticePublishPanel({
  courseId,
  quizId,
}: PracticePublishPanelProps) {
  const t = useTranslations("teacher.practice.publish");
  const { data: quiz } = useQuiz(quizId);
  const publish = usePublishQuiz(courseId);
  const [failed, setFailed] = useState(false);

  const questionCount = quiz?.questions.length ?? 0;
  const hasQuestions = questionCount > 0;
  const published = quiz?.is_published ?? false;

  const doPublish = useCallback(async () => {
    setFailed(false);
    try {
      await publish.mutateAsync(quizId);
    } catch {
      setFailed(true);
    }
  }, [publish, quizId]);

  return (
    <div className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="space-y-1">
        <h3 className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h3>
        <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </div>

      <ul className="space-y-2">
        <ReadyRow
          done={hasQuestions}
          label={t("checklist.questions", { count: questionCount })}
        />
        <li className="flex items-start gap-2 text-[12px] leading-snug text-[var(--color-text-secondary)]">
          <Info
            aria-hidden="true"
            className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
          />
          {t("checklist.noScore")}
        </li>
      </ul>

      {published ? (
        <StateBanner tone="success" title={t("publishedTitle")} reason={t("publishedReason")} />
      ) : null}

      {failed ? (
        <p role="alert" className="text-[12px] text-[var(--color-error)]">
          {t("publishError")}
        </p>
      ) : null}

      <Button
        type="button"
        className="w-full"
        disabled={!hasQuestions || publish.isPending}
        onClick={() => void doPublish()}
      >
        {publish.isPending ? (
          <Loader2 aria-hidden="true" className="size-4 animate-spin" />
        ) : (
          <Rocket aria-hidden="true" className="size-4" />
        )}
        {publish.isPending
          ? t("publishing")
          : published
            ? t("republish")
            : t("publish")}
      </Button>
    </div>
  );
}

function ReadyRow({ done, label }: { readonly done: boolean; readonly label: string }) {
  return (
    <li className="flex items-start gap-2 text-[12px] leading-snug">
      <CheckCircle2
        aria-hidden="true"
        className={
          done
            ? "mt-0.5 size-4 shrink-0 text-[var(--color-success)]"
            : "mt-0.5 size-4 shrink-0 text-[var(--color-text-muted)]"
        }
      />
      <span className="text-[var(--color-text)]">{label}</span>
    </li>
  );
}
