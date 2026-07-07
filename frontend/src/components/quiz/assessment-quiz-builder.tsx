"use client";

import { useCallback, useState, type ReactNode } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BarChart3,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { EmptyState, StateBanner } from "@/components/patterns";
import { QuizQuestionEditor } from "@/components/quiz/quiz-question-editor";
import { GenerateQuizDialog } from "@/components/quiz/generate-quiz-dialog";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import {
  useQuiz,
  type QuestionResponse,
  type QuizDetailResponse,
} from "@/hooks/use-quizzes";
import type { AssessmentConfig } from "@/components/quiz/assessment-config";

/** Question renderers with a dedicated `typeLabel.*` i18n key (B7, Decision 2). */
const KNOWN_QUESTION_TYPES = new Set([
  "multiple_choice",
  "true_false",
  "matching",
  "ordering",
  "short_answer",
]);

/** The default shape for a brand-new multiple-choice question. */
const BLANK_QUESTION = {
  question_text: "",
  options: { A: "", B: "", C: "", D: "" } as Record<string, string>,
  correct_answer: "A",
  explanation: null as string | null,
  difficulty: "medium",
};

interface AssessmentQuizBuilderProps {
  readonly courseId: string;
  readonly quizId: string;
  readonly config: AssessmentConfig;
  /**
   * The per-surface publish panel (practice: `PracticePublishPanel`; graded:
   * `QuizPublishPanel` with the score-policy gate, F3). Rendered in the right
   * rail so the review and publish steps sit side-by-side (Figma T061/T063).
   */
  readonly publishPanel: ReactNode;
}

/**
 * T061/T062 (practice) & T065/T066 (graded) — the shared question builder /
 * review. Loads the quiz detail, lists each question with a type badge, and
 * supports add / edit (via the reused `QuizQuestionEditor`) / delete plus the
 * shared `GenerateQuizDialog` stamped with this surface's `assessment_purpose`.
 * The publish step is injected as `publishPanel` so practice (no gate) and
 * graded (score-policy gate) reuse identical review chrome.
 */
export function AssessmentQuizBuilder({
  courseId,
  quizId,
  config,
  publishPanel,
}: AssessmentQuizBuilderProps) {
  const t = useTranslations(config.ns);
  const { getToken } = useAuth();
  const qc = useQueryClient();
  const { data: quiz, isLoading, error } = useQuiz(quizId);

  const [generateOpen, setGenerateOpen] = useState(false);
  const [editing, setEditing] = useState<QuestionResponse | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuestionResponse | null>(
    null
  );

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["quizzes", "detail", quizId] });
  }, [qc, quizId]);

  const saveQuestion = useMutation({
    mutationFn: async (patch: {
      question_text: string;
      options: Record<string, string>;
      correct_answer: string;
      explanation: string | null;
      difficulty: string;
    }) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const isNew = editing === "new";
      const path = isNew
        ? `/quizzes/${quizId}/questions`
        : `/questions/${(editing as QuestionResponse).id}`;
      await apiFetch<ApiEnvelope<unknown>>(path, {
        token,
        method: isNew ? "POST" : "PATCH",
        body: JSON.stringify({ type: "multiple_choice", ...patch }),
      });
    },
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
  });

  const deleteQuestion = useMutation({
    mutationFn: async (questionId: string) => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<null>>(`/questions/${questionId}`, {
        token,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      invalidate();
      setDeleteTarget(null);
    },
  });

  const backHref = config.base(courseId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !quiz) {
    return (
      <StateBanner
        tone="warning"
        title={t("builder.notFoundTitle")}
        reason={t("builder.notFound")}
        action={
          <Link
            href={backHref}
            className="text-[13px] font-medium text-[var(--color-primary)] hover:underline"
          >
            {t("builder.back")}
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          href={backHref}
          className="inline-flex items-center gap-1 text-[13px] text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
        >
          <ArrowLeft aria-hidden="true" className="size-3.5" />
          {t("builder.back")}
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h2 className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
              {quiz.title}
            </h2>
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              {t("builder.subtitle")}
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            render={<Link href={`${backHref}/${quizId}/results`} />}
          >
            <BarChart3 aria-hidden="true" className="size-4" />
            {t("builder.viewResults")}
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start">
        <section className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("builder.questionsTitle")}
            </h3>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setGenerateOpen(true)}
              >
                <Sparkles aria-hidden="true" className="size-4" />
                {t("builder.generate")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEditing("new")}
              >
                <Plus aria-hidden="true" className="size-4" />
                {t("builder.addQuestion")}
              </Button>
            </div>
          </div>

          {quiz.questions.length === 0 ? (
            <EmptyState
              variant="empty"
              icon={Sparkles}
              title={t("builder.empty.title")}
              reason={t("builder.empty.reason")}
              action={
                <Button type="button" onClick={() => setGenerateOpen(true)}>
                  <Sparkles aria-hidden="true" className="size-4" />
                  {t("builder.generate")}
                </Button>
              }
            />
          ) : (
            <ol className="space-y-2.5">
              {quiz.questions.map((question, index) => (
                <QuestionRow
                  key={question.id}
                  index={index}
                  question={question}
                  onEdit={() => setEditing(question)}
                  onDelete={() => setDeleteTarget(question)}
                  t={t}
                />
              ))}
            </ol>
          )}
        </section>

        <aside className="lg:sticky lg:top-6">{publishPanel}</aside>
      </div>

      <QuizQuestionEditor
        open={editing !== null}
        initial={
          editing && editing !== "new"
            ? {
                question_text: editing.question_text,
                options: editing.options ?? BLANK_QUESTION.options,
                correct_answer: editing.correct_answer ?? "A",
                explanation: editing.explanation,
                difficulty: "medium",
              }
            : BLANK_QUESTION
        }
        isSaving={saveQuestion.isPending}
        onCancel={() => setEditing(null)}
        onSubmit={(patch) => saveQuestion.mutate(patch)}
      />

      <GenerateQuizDialog
        courseId={courseId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
        assessmentPurpose={config.purpose}
      />

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("builder.deleteConfirm.title")}</DialogTitle>
            <DialogDescription>
              {t("builder.deleteConfirm.body")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteQuestion.isPending}
            >
              {t("builder.deleteConfirm.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteTarget && deleteQuestion.mutate(deleteTarget.id)
              }
              disabled={deleteQuestion.isPending}
            >
              {t("builder.deleteConfirm.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface QuestionRowProps {
  readonly index: number;
  readonly question: QuestionResponse;
  readonly onEdit: () => void;
  readonly onDelete: () => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function QuestionRow({ index, question, onEdit, onDelete, t }: QuestionRowProps) {
  const isMc = question.type === "multiple_choice";
  return (
    <li className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-[var(--color-surface-hover)] text-xs font-medium text-[var(--color-text-muted)]">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <p className="text-[14px] font-medium leading-snug text-[var(--color-text)]">
          {question.question_text}
        </p>
        <Badge variant="outline" className="text-[11px]">
          {KNOWN_QUESTION_TYPES.has(question.type)
            ? t(`typeLabel.${question.type}`)
            : t("typeLabel.other")}
        </Badge>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {isMc ? (
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            aria-label={t("builder.editQuestion")}
            onClick={onEdit}
          >
            <Pencil aria-hidden="true" className="size-4" />
          </Button>
        ) : null}
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label={t("builder.deleteQuestion")}
          onClick={onDelete}
        >
          <Trash2 aria-hidden="true" className="size-4 text-[var(--color-error)]" />
        </Button>
      </div>
    </li>
  );
}

export type { QuizDetailResponse };
