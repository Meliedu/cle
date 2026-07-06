"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  ClipboardList,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Sparkles,
  Target,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { EmptyState } from "@/components/patterns";
import {
  BLOOM_LEVELS,
  useCreateObjective,
  useDeleteObjective,
  useObjectiveConcepts,
  useObjectives,
  useUpdateObjective,
  type BloomLevel,
  type Objective,
} from "@/hooks/use-objectives";
import { useSetStep } from "@/hooks/use-setup";

interface StepIloProps {
  readonly courseId: string;
  /** Fired after the `ilo_map` checklist flag is set. */
  readonly onComplete?: () => void;
}

interface IloDraft {
  readonly statement: string;
  readonly bloomLevel: BloomLevel | "";
}

const EMPTY_DRAFT: IloDraft = { statement: "", bloomLevel: "" };

const SELECT_CLASS =
  "h-8 w-full min-w-0 rounded-lg border border-[var(--color-border)] bg-transparent px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";

/**
 * T020 — ILO-map-builder step. Reuses the existing `objectives.py` router
 * (`useObjectives` + create/update/delete) to list, add, edit, and remove
 * intended learning outcomes (statement, Bloom level, order) and surfaces each
 * ILO's concept links read-only via `/concept-tags/objective/{id}`. Flips the
 * `ilo_map` checklist flag once at least one objective exists.
 */
export function StepIlo({ courseId, onComplete }: StepIloProps) {
  const t = useTranslations("teacher.setup.ilo");
  const { data: objectives, isLoading } = useObjectives(courseId);
  const createObjective = useCreateObjective(courseId);
  const updateObjective = useUpdateObjective(courseId);
  const deleteObjective = useDeleteObjective(courseId);
  const setStep = useSetStep(courseId);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<IloDraft>(EMPTY_DRAFT);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const ilos = useMemo(
    () => [...(objectives ?? [])].sort((a, b) => a.order_index - b.order_index),
    [objectives]
  );
  const hasIlos = ilos.length > 0;
  const nextOrder = useMemo(
    () => ilos.reduce((max, o) => Math.max(max, o.order_index), -1) + 1,
    [ilos]
  );

  const resetForm = useCallback(() => {
    setEditingId(null);
    setDraft(EMPTY_DRAFT);
    setFormError(null);
  }, []);

  const startEdit = useCallback((objective: Objective) => {
    setEditingId(objective.id);
    setFormError(null);
    setDraft({
      statement: objective.statement,
      bloomLevel: objective.bloom_level ?? "",
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    setFormError(null);
    const statement = draft.statement.trim();
    if (!statement) {
      setFormError(t("form.statementRequired"));
      return;
    }
    const bloom = draft.bloomLevel === "" ? null : draft.bloomLevel;
    try {
      if (editingId) {
        await updateObjective.mutateAsync({
          objectiveId: editingId,
          patch: { statement, bloom_level: bloom },
        });
      } else {
        await createObjective.mutateAsync({
          statement,
          bloom_level: bloom,
          order_index: nextOrder,
        });
      }
      resetForm();
    } catch {
      setFormError(t("form.saveError"));
    }
  }, [draft, editingId, nextOrder, createObjective, updateObjective, resetForm, t]);

  const handleDelete = useCallback(
    async (objectiveId: string) => {
      setActionError(null);
      try {
        await deleteObjective.mutateAsync(objectiveId);
        if (editingId === objectiveId) resetForm();
      } catch {
        setActionError(t("deleteError"));
      }
    },
    [deleteObjective, editingId, resetForm, t]
  );

  const flipDone = useCallback(async () => {
    setActionError(null);
    try {
      await setStep.mutateAsync({ step: "ilo_map", done: true });
      onComplete?.();
    } catch {
      setActionError(t("continueError"));
    }
  }, [setStep, onComplete, t]);

  const isSaving = createObjective.isPending || updateObjective.isPending;
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

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void handleSubmit();
          }}
          noValidate
          className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5"
        >
          <p className="text-[13px] font-semibold text-[var(--color-text)]">
            {editingId ? t("form.editTitle") : t("form.addTitle")}
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="ilo-statement">{t("form.statement")}</Label>
            <Textarea
              id="ilo-statement"
              rows={2}
              placeholder={t("form.statementPlaceholder")}
              value={draft.statement}
              onChange={(e) => setDraft((prev) => ({ ...prev, statement: e.target.value }))}
            />
          </div>

          <div className="space-y-1.5 sm:max-w-[16rem]">
            <Label htmlFor="ilo-bloom">{t("form.bloom")}</Label>
            <select
              id="ilo-bloom"
              className={SELECT_CLASS}
              value={draft.bloomLevel}
              onChange={(e) =>
                setDraft((prev) => ({ ...prev, bloomLevel: e.target.value as BloomLevel | "" }))
              }
            >
              <option value="">{t("form.bloomNone")}</option>
              {BLOOM_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {t(`bloom.${level}`)}
                </option>
              ))}
            </select>
          </div>

          {formError ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {formError}
            </p>
          ) : null}

          <div className="flex items-center gap-3">
            <Button type="submit" size="sm" disabled={isSaving}>
              {isSaving ? (
                <Loader2 aria-hidden="true" className="animate-spin" />
              ) : (
                <Plus aria-hidden="true" />
              )}
              {editingId ? t("form.saveEdit") : t("form.add")}
            </Button>
            {editingId ? (
              <Button type="button" size="sm" variant="ghost" onClick={resetForm}>
                {t("form.cancel")}
              </Button>
            ) : null}
          </div>
        </form>

        <section aria-label={t("listLabel")} className="space-y-3">
          {isLoading ? (
            <EmptyState variant="waiting" title={t("loading")} />
          ) : !hasIlos ? (
            <EmptyState
              variant="empty"
              icon={Target}
              title={t("empty.title")}
              reason={t("empty.reason")}
            />
          ) : (
            <ul className="space-y-2.5">
              {ilos.map((objective, position) => (
                <IloRow
                  key={objective.id}
                  objective={objective}
                  position={position + 1}
                  onEdit={startEdit}
                  onDelete={handleDelete}
                  t={t}
                />
              ))}
            </ul>
          )}
        </section>

        {actionError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {actionError}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            size="lg"
            disabled={!hasIlos || isFlipping}
            onClick={() => void flipDone()}
          >
            {isFlipping ? <Loader2 aria-hidden="true" className="animate-spin" /> : null}
            {t("approve")}
          </Button>
        </div>
      </div>

      <UsedForAside t={t} />
    </div>
  );
}

interface IloRowProps {
  readonly objective: Objective;
  readonly position: number;
  readonly onEdit: (objective: Objective) => void;
  readonly onDelete: (objectiveId: string) => void;
  readonly t: ReturnType<typeof useTranslations>;
}

function IloRow({ objective, position, onEdit, onDelete, t }: IloRowProps) {
  const { data: concepts } = useObjectiveConcepts(objective.id);

  return (
    <li className="space-y-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
      <div className="flex items-start gap-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-primary-light)] text-[12px] font-semibold text-[var(--color-primary-hover)]">
          {position}
        </span>
        <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-[var(--color-text)]">
          {objective.statement}
        </p>
        <div className="flex shrink-0 items-center gap-0.5">
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            aria-label={t("editIlo")}
            onClick={() => onEdit(objective)}
          >
            <Pencil aria-hidden="true" />
          </Button>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            aria-label={t("deleteIlo")}
            onClick={() => onDelete(objective.id)}
          >
            <Trash2 aria-hidden="true" className="text-[var(--color-error)]" />
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 pl-9">
        {objective.bloom_level ? (
          <Badge variant="secondary">{t(`bloom.${objective.bloom_level}`)}</Badge>
        ) : null}
        {(concepts ?? []).map((concept) => (
          <Badge key={concept.id} variant="outline">
            {concept.name}
          </Badge>
        ))}
      </div>
    </li>
  );
}

function UsedForAside({ t }: { t: ReturnType<typeof useTranslations> }) {
  const items = [
    { icon: ClipboardList, key: "sessions" },
    { icon: Sparkles, key: "checkpoints" },
    { icon: MessageSquare, key: "practice" },
  ] as const;

  return (
    <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        {t("aside.title")}
      </p>
      <ul className="mt-4 space-y-4">
        {items.map(({ icon: Icon, key }) => (
          <li key={key} className="flex gap-3">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
              <Icon aria-hidden="true" strokeWidth={1.85} className="size-4" />
            </span>
            <div className="min-w-0 space-y-0.5">
              <p className="text-[13px] font-medium text-[var(--color-text)]">
                {t(`aside.${key}.title`)}
              </p>
              <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
                {t(`aside.${key}.description`)}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
