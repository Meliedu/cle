"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Loader2, Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import {
  useQuiz,
  usePublishQuiz,
  ScorePolicyError,
} from "@/hooks/use-quizzes";
import {
  ScorePolicyPanel,
  policyFieldId,
  EMPTY_SCORE_POLICY,
  type ScorePolicyField,
  type ScorePolicyValue,
} from "@/components/quiz/score-policy-panel";
import { ScorePolicyBlockedBanner } from "@/components/quiz/score-policy-blocked-banner";

interface QuizPublishPanelProps {
  readonly courseId: string;
  readonly quizId: string;
}

/** ISO 8601 → the `datetime-local` input shape (`YYYY-MM-DDTHH:mm`). */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

/** `datetime-local` value → ISO 8601, or null when blank. */
function toIso(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/**
 * T067 — graded quiz publish with the score-policy gate. Collects the policy
 * via `ScorePolicyPanel`, persists it, then publishes through `usePublishQuiz`.
 * A graded publish missing any gated field throws `ScorePolicyError`; its
 * `missing[]` is mapped to the `ScorePolicyBlockedBanner` (blocked tone + jump-
 * to-field), mirroring P1's setup gate (Decision 7). Practice's counterpart
 * (`PracticePublishPanel`) skips this entirely.
 */
export function QuizPublishPanel({ courseId, quizId }: QuizPublishPanelProps) {
  const t = useTranslations("teacher.quiz.publish");
  const { getToken } = useAuth();
  const { data: quiz } = useQuiz(quizId);
  const publish = usePublishQuiz(courseId);

  const [policy, setPolicy] = useState<ScorePolicyValue>(EMPTY_SCORE_POLICY);
  const [missing, setMissing] = useState<ReadonlySet<ScorePolicyField>>(
    new Set()
  );
  const [genericError, setGenericError] = useState(false);

  // Prefill from the persisted quiz once it loads (score_category_id /
  // grading_mode may be absent from the detail read until the backend surfaces
  // them; guarded with `?? ""`).
  useEffect(() => {
    if (!quiz) return;
    setPolicy({
      score_category_id: quiz.score_category_id ?? "",
      points: quiz.points != null ? String(quiz.points) : "",
      grading_mode: quiz.grading_mode ?? "",
      late_rule: quiz.late_rule ?? "",
      due_at: toLocalInput(quiz.due_at),
      close_at: toLocalInput(quiz.close_at),
    });
  }, [quiz]);

  const jumpToField = useCallback((field: ScorePolicyField) => {
    if (typeof document === "undefined") return;
    const el = document.getElementById(policyFieldId(field));
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    (el as HTMLElement | null)?.focus?.();
  }, []);

  const doPublish = useCallback(async () => {
    setGenericError(false);
    setMissing(new Set());

    // Persist the policy before publishing so the gate reads the latest values.
    // Sent even for fields the backend may not yet accept (forward-compatible;
    // unknown fields are ignored by the update schema).
    try {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      await apiFetch<ApiEnvelope<unknown>>(`/quizzes/${quizId}`, {
        token,
        method: "PUT",
        body: JSON.stringify({
          score_category_id: policy.score_category_id || null,
          points: policy.points ? Number(policy.points) : null,
          grading_mode: policy.grading_mode || null,
          late_rule: policy.late_rule || null,
          due_at: toIso(policy.due_at),
          close_at: toIso(policy.close_at),
        }),
      });
    } catch {
      setGenericError(true);
      return;
    }

    try {
      await publish.mutateAsync(quizId);
    } catch (err) {
      if (err instanceof ScorePolicyError) {
        setMissing(mapMissing(err.missing));
        return;
      }
      setGenericError(true);
    }
  }, [getToken, quizId, policy, publish]);

  const questionCount = quiz?.questions.length ?? 0;
  const hasQuestions = questionCount > 0;
  const published = quiz?.is_published ?? false;

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

      <ScorePolicyPanel
        courseId={courseId}
        value={policy}
        onChange={setPolicy}
        missing={missing}
        disabled={publish.isPending}
      />

      <ul className="space-y-2 border-t border-[var(--color-border)] pt-4">
        <li className="flex items-start gap-2 text-[12px] leading-snug">
          <CheckCircle2
            aria-hidden="true"
            className={
              hasQuestions
                ? "mt-0.5 size-4 shrink-0 text-[var(--color-success)]"
                : "mt-0.5 size-4 shrink-0 text-[var(--color-text-muted)]"
            }
          />
          <span className="text-[var(--color-text)]">
            {t("checklist.questions", { count: questionCount })}
          </span>
        </li>
      </ul>

      {missing.size > 0 ? (
        <ScorePolicyBlockedBanner
          missing={[...missing]}
          onJump={jumpToField}
        />
      ) : null}

      {published && missing.size === 0 ? (
        <StateBanner
          tone="success"
          title={t("publishedTitle")}
          reason={t("publishedReason")}
        />
      ) : null}

      {genericError ? (
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

/** Narrow a backend `missing[]` payload to the known gated fields. */
function mapMissing(missing: readonly string[]): ReadonlySet<ScorePolicyField> {
  const known: readonly ScorePolicyField[] = [
    "score_category_id",
    "points",
    "grading_mode",
    "deadline",
  ];
  return new Set(known.filter((f) => missing.includes(f)));
}
