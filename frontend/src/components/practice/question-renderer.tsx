"use client";

import { useTranslations } from "next-intl";
import { ArrowDown, ArrowUp } from "lucide-react";

import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import {
  matchingColumns,
  normalizeChoiceList,
  reorder,
  type AnswerDraft,
  type Choice,
  type QuestionType,
} from "./answer-encoding";

/** The minimal question shape a renderer needs (student-safe: no answer key). */
export interface RenderableQuestion {
  readonly id: string;
  readonly type: QuestionType;
  readonly questionText: string;
  readonly options: unknown;
}

interface QuestionRendererProps {
  readonly question: RenderableQuestion;
  readonly draft: AnswerDraft;
  readonly onChange: (draft: AnswerDraft) => void;
  /** Disable inputs once the attempt is submitted (feedback view). */
  readonly disabled?: boolean;
}

/**
 * Dispatch on the free-string `Question.type` (Decision 2). Each branch owns its
 * own accessible input and emits an `AnswerDraft` the shared encoder turns into
 * the exact backend wire shape. Keyboard-navigable throughout; motion is gated
 * behind `motion-reduce:*` so `prefers-reduced-motion` users get no transitions.
 */
export function QuestionRenderer({
  question,
  draft,
  onChange,
  disabled = false,
}: QuestionRendererProps) {
  if (draft.type === "matching" && question.type === "matching") {
    return (
      <MatchingRenderer
        question={question}
        map={draft.map}
        disabled={disabled}
        onChange={(map) => onChange({ type: "matching", map })}
      />
    );
  }
  if (draft.type === "ordering" && question.type === "ordering") {
    return (
      <OrderingRenderer
        question={question}
        order={draft.order}
        disabled={disabled}
        onChange={(order) => onChange({ type: "ordering", order })}
      />
    );
  }
  if (draft.type === "short_answer" && question.type === "short_answer") {
    return (
      <ShortAnswerRenderer
        text={draft.text}
        disabled={disabled}
        onChange={(text) => onChange({ type: "short_answer", text })}
      />
    );
  }
  return (
    <MultipleChoiceRenderer
      question={question}
      value={draft.type === "multiple_choice" ? draft.key : null}
      disabled={disabled}
      onChange={(key) => onChange({ type: "multiple_choice", key })}
    />
  );
}

/* -------------------------------------------------------------------------- */
/*  multiple_choice — emits the option KEY string (e.g. "b")                   */
/* -------------------------------------------------------------------------- */

function MultipleChoiceRenderer({
  question,
  value,
  disabled,
  onChange,
}: {
  readonly question: RenderableQuestion;
  readonly value: string | null;
  readonly disabled: boolean;
  readonly onChange: (key: string) => void;
}) {
  const t = useTranslations("student.practice");
  const choices = normalizeChoiceList(question.options);

  return (
    <fieldset
      className="space-y-3"
      role="radiogroup"
      aria-label={t("renderer.mcLegend")}
    >
      {choices.map((choice) => {
        const selected = value === choice.id;
        return (
          <button
            key={choice.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(choice.id)}
            className={cn(
              "flex w-full items-center gap-3 rounded-[var(--radius-lg)] border p-4 text-left outline-none transition-colors duration-[var(--duration-fast)] motion-reduce:transition-none",
              "focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30 disabled:cursor-default disabled:opacity-70",
              selected
                ? "border-[var(--color-primary)] bg-[var(--color-primary-light)]"
                : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)]"
            )}
            style={{ minHeight: "48px" }}
          >
            <span
              aria-hidden="true"
              className={cn(
                "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold uppercase",
                selected
                  ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                  : "border-[var(--color-border)] text-[var(--color-text-muted)]"
              )}
            >
              {choice.id}
            </span>
            <span
              className={cn(
                "flex-1 text-sm font-medium",
                selected
                  ? "text-[var(--color-primary)]"
                  : "text-[var(--color-text)]"
              )}
            >
              {choice.label}
            </span>
          </button>
        );
      })}
    </fieldset>
  );
}

/* -------------------------------------------------------------------------- */
/*  matching — emits JSON.stringify({left_id: right_id})                       */
/* -------------------------------------------------------------------------- */

function MatchingRenderer({
  question,
  map,
  disabled,
  onChange,
}: {
  readonly question: RenderableQuestion;
  readonly map: Readonly<Record<string, string>>;
  readonly disabled: boolean;
  readonly onChange: (map: Record<string, string>) => void;
}) {
  const t = useTranslations("student.practice");
  const { left, right } = matchingColumns(question.options);

  const setMatch = (leftId: string, rightId: string) => {
    const next = { ...map };
    if (rightId === "") delete next[leftId];
    else next[leftId] = rightId;
    onChange(next);
  };

  return (
    <ul className="space-y-3">
      {left.map((leftItem) => {
        const selectId = `match-${question.id}-${leftItem.id}`;
        return (
          <li
            key={leftItem.id}
            className="flex flex-col gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:flex-row sm:items-center sm:gap-4"
          >
            <label
              htmlFor={selectId}
              className="flex-1 text-sm font-medium text-[var(--color-text)]"
            >
              {leftItem.label}
            </label>
            <select
              id={selectId}
              disabled={disabled}
              value={map[leftItem.id] ?? ""}
              onChange={(event) => setMatch(leftItem.id, event.target.value)}
              className={cn(
                "h-10 w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-sm text-[var(--color-text)] outline-none",
                "focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30 disabled:opacity-70 sm:w-56"
              )}
            >
              <option value="">{t("renderer.matchPlaceholder")}</option>
              {right.map((rightItem) => (
                <option key={rightItem.id} value={rightItem.id}>
                  {rightItem.label}
                </option>
              ))}
            </select>
          </li>
        );
      })}
    </ul>
  );
}

/* -------------------------------------------------------------------------- */
/*  ordering — emits JSON.stringify([...ids in chosen order])                  */
/* -------------------------------------------------------------------------- */

function OrderingRenderer({
  question,
  order,
  disabled,
  onChange,
}: {
  readonly question: RenderableQuestion;
  readonly order: readonly string[];
  readonly disabled: boolean;
  readonly onChange: (order: string[]) => void;
}) {
  const t = useTranslations("student.practice");
  const byId = new Map(
    normalizeChoiceList(question.options).map((choice) => [choice.id, choice])
  );

  const move = (index: number, direction: -1 | 1) =>
    onChange(reorder(order, index, direction));

  return (
    <ol className="space-y-2" aria-label={t("renderer.orderingLegend")}>
      {order.map((id, index) => {
        const choice: Choice = byId.get(id) ?? { id, label: id };
        return (
          <li
            key={id}
            className="flex items-center gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
          >
            <span
              aria-hidden="true"
              className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-xs font-semibold text-[var(--color-primary)]"
            >
              {index + 1}
            </span>
            <span className="flex-1 text-sm font-medium text-[var(--color-text)]">
              {choice.label}
            </span>
            <span className="flex shrink-0 gap-1">
              <button
                type="button"
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                aria-label={t("renderer.moveUp", { item: choice.label })}
                className="flex size-8 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-muted)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30 disabled:opacity-40 motion-reduce:transition-none"
              >
                <ArrowUp className="size-4" />
              </button>
              <button
                type="button"
                disabled={disabled || index === order.length - 1}
                onClick={() => move(index, 1)}
                aria-label={t("renderer.moveDown", { item: choice.label })}
                className="flex size-8 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-muted)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/30 disabled:opacity-40 motion-reduce:transition-none"
              >
                <ArrowDown className="size-4" />
              </button>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/*  short_answer — emits the raw typed text                                    */
/* -------------------------------------------------------------------------- */

function ShortAnswerRenderer({
  text,
  disabled,
  onChange,
}: {
  readonly text: string;
  readonly disabled: boolean;
  readonly onChange: (text: string) => void;
}) {
  const t = useTranslations("student.practice");
  return (
    <div className="space-y-1.5">
      <label
        htmlFor="short-answer-input"
        className="text-[13px] font-medium text-[var(--color-text-secondary)]"
      >
        {t("renderer.shortAnswerLabel")}
      </label>
      <Textarea
        id="short-answer-input"
        value={text}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t("renderer.shortAnswerPlaceholder")}
        rows={3}
      />
    </div>
  );
}
