"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Plus, Sparkles, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState } from "@/components/patterns";
import {
  useCreateScoreCategory,
  useDeleteScoreCategory,
  useScoreCategories,
  useSetStep,
  useUpdateScoreCategory,
  type ScoreCategory,
} from "@/hooks/use-setup";

interface StepScorePolicyProps {
  readonly courseId: string;
  /** Fired after the `score_policy` checklist flag is set. */
  readonly onComplete?: () => void;
}

/** `null` weight = ungraded; render an empty field the teacher can fill in. */
function weightToInput(weight: number | null): string {
  return weight === null || weight === undefined ? "" : String(weight);
}

/**
 * T024 — score-policy step. Lists the pilot's seeded score categories
 * (`useScoreCategories`, Task 10) and lets the teacher rename them, adjust each
 * category's weight toward the course record, add new categories, or remove the
 * ones they do not use — all through the `scores.py` CRUD router. "Continue"
 * flips the `score_policy` checklist flag. Grade export + student scores are P5;
 * this step only shapes the category list.
 */
export function StepScorePolicy({ courseId, onComplete }: StepScorePolicyProps) {
  const t = useTranslations("teacher.setup.scorePolicy");
  const { data: categories, isLoading } = useScoreCategories(courseId);
  const createCategory = useCreateScoreCategory(courseId);
  const setStep = useSetStep(courseId);

  const [actionError, setActionError] = useState<string | null>(null);

  const addCategory = useCallback(async () => {
    setActionError(null);
    try {
      await createCategory.mutateAsync({ name: t("newCategoryName"), weight: null });
    } catch {
      setActionError(t("addError"));
    }
  }, [createCategory, t]);

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "score_policy", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const rows = categories ?? [];
  const hasRows = rows.length > 0;
  const isFlipping = setStep.isPending;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
      <div className="space-y-6">
        <div className="space-y-1.5">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="max-w-[56ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>

        <div className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[13px] font-semibold text-[var(--color-text)]">
              {t("categoriesTitle")}
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={createCategory.isPending}
              onClick={() => void addCategory()}
            >
              {createCategory.isPending ? (
                <Loader2 aria-hidden="true" className="animate-spin" />
              ) : (
                <Plus aria-hidden="true" />
              )}
              {t("addCategory")}
            </Button>
          </div>

          {isLoading ? (
            <EmptyState variant="waiting" title={t("loading")} />
          ) : !hasRows ? (
            <EmptyState
              variant="empty"
              title={t("empty.title")}
              reason={t("empty.reason")}
            />
          ) : (
            <ul className="space-y-2.5">
              {rows.map((category) => (
                <CategoryRow
                  key={category.id}
                  courseId={courseId}
                  category={category}
                  onError={setActionError}
                  t={t}
                />
              ))}
            </ul>
          )}
        </div>

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
            {t("continue")}
          </Button>
        </div>
      </div>

      <MotivationAside t={t} />
    </div>
  );
}

interface CategoryRowProps {
  readonly courseId: string;
  readonly category: ScoreCategory;
  readonly onError: (message: string | null) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function CategoryRow({ courseId, category, onError, t }: CategoryRowProps) {
  const update = useUpdateScoreCategory(courseId);
  const remove = useDeleteScoreCategory(courseId);
  const [name, setName] = useState(category.name);
  const [weight, setWeight] = useState(weightToInput(category.weight));

  const dirty =
    name.trim() !== category.name || weight !== weightToInput(category.weight);

  const save = useCallback(async () => {
    onError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      onError(t("nameRequired"));
      return;
    }
    const parsedWeight = weight.trim() === "" ? null : Number(weight);
    if (parsedWeight !== null && (!Number.isFinite(parsedWeight) || parsedWeight < 0)) {
      onError(t("weightInvalid"));
      return;
    }
    try {
      await update.mutateAsync({ id: category.id, name: trimmed, weight: parsedWeight });
    } catch {
      onError(t("saveError"));
    }
  }, [name, weight, update, category.id, onError, t]);

  const confirmRemove = useCallback(async () => {
    onError(null);
    try {
      await remove.mutateAsync(category.id);
    } catch {
      onError(t("removeError"));
    }
  }, [remove, category.id, onError, t]);

  return (
    <li className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] p-3 sm:grid-cols-[minmax(0,1fr)_7rem_auto] sm:items-end">
      <div className="space-y-1.5">
        <Label htmlFor={`cat-name-${category.id}`}>{t("nameLabel")}</Label>
        <Input
          id={`cat-name-${category.id}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`cat-weight-${category.id}`}>{t("weightLabel")}</Label>
        <Input
          id={`cat-weight-${category.id}`}
          type="number"
          min={0}
          inputMode="decimal"
          placeholder={t("ungraded")}
          value={weight}
          onChange={(e) => setWeight(e.target.value)}
        />
      </div>
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!dirty || update.isPending}
          onClick={() => void save()}
        >
          {update.isPending ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
          {t("save")}
        </Button>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          aria-label={t("removeCategory", { name: category.name })}
          disabled={remove.isPending}
          onClick={() => void confirmRemove()}
        >
          <Trash2 aria-hidden="true" className="text-[var(--color-error)]" />
        </Button>
      </div>
    </li>
  );
}

function MotivationAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const points = ["grounded", "visible", "flexible"] as const;
  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <ul className="mt-4 space-y-3">
        {points.map((point) => (
          <li key={point} className="flex gap-2.5">
            <Sparkles
              aria-hidden="true"
              strokeWidth={1.85}
              className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
            />
            <div className="space-y-0.5">
              <p className="text-[13px] font-medium text-[var(--color-text)]">
                {t(`aside.${point}.title`)}
              </p>
              <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
                {t(`aside.${point}.description`)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
