"use client";

import { useCallback, useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PlacementItem } from "@/hooks/use-placement";

interface PlacementQuestionProps {
  readonly item: PlacementItem;
  readonly value: string | null;
  readonly onChange: (value: string | null) => void;
  /** Times the learner has played this item's audio, if it has any. */
  readonly playCount?: number;
  readonly onPlay?: () => void;
  /**
   * Whether approved recordings exist for this form. When false the listening
   * script is read aloud by a proctor, so no play control is offered.
   */
  readonly audioAvailable?: boolean;
}

/**
 * One question. Two response surfaces, chosen by the item's own format.
 *
 * Ordinary items are a radio group. Ordering items are not: "put these three in
 * order" is not a single choice, and forcing it into radios would misreport the
 * task to assistive tech. They render as three ordered slots the learner fills
 * by picking a fragment for each position, which is the same interaction the
 * paper booklet describes ("Order / 顺序: __ - __ - __").
 */
export function PlacementQuestion({
  item,
  value,
  onChange,
  playCount = 0,
  onPlay,
  audioAvailable = false,
}: PlacementQuestionProps) {
  const t = useTranslations("placement.sitting");
  const groupId = useId();

  if (item.response_format === "sequence") {
    return (
      <SequenceQuestion
        item={item}
        value={value}
        onChange={onChange}
        groupId={groupId}
      />
    );
  }

  const playsAllowed = item.audio_playback ?? 0;
  const playsLeft = Math.max(0, playsAllowed - playCount);

  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">
        {t("questionLegend", { number: item.question_number })}
      </legend>

      {/* No approved recordings yet, so a play button would produce silence and
          a learner would burn exam minutes deciding their audio is broken. Say
          what actually happens instead: a proctor reads the script twice. */}
      {item.audio_playback && !audioAvailable ? (
        <p className="flex items-start gap-2 rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] p-3 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          <Volume2 aria-hidden="true" className="mt-0.5 size-4 shrink-0" strokeWidth={1.9} />
          {t("proctorRead", { plays: playsAllowed })}
        </p>
      ) : null}

      {item.audio_playback && audioAvailable ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={onPlay}
            disabled={playsLeft === 0}
          >
            <Volume2 aria-hidden="true" />
            {t("playAudio")}
          </Button>
          <span className="text-[13px] text-[var(--color-text-secondary)]">
            {t("playsLeft", { count: playsLeft, total: playsAllowed })}
          </span>
        </div>
      ) : null}

      <Stimulus item={item} />

      <div className="space-y-2">
        {item.options.map((option) => {
          const id = `${groupId}-${option.letter}`;
          const selected = value === option.letter;
          return (
            <label
              key={option.letter}
              htmlFor={id}
              className={cn(
                "flex cursor-pointer items-start gap-3 rounded-[var(--radius-lg)] border p-4",
                "pointer-coarse:min-h-11 transition-colors duration-150",
                "focus-within:ring-2 focus-within:ring-[var(--color-primary)]/40",
                selected
                  ? "border-[var(--color-primary)] bg-[var(--color-primary)]/8"
                  : "border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-hover)]"
              )}
            >
              <input
                id={id}
                type="radio"
                name={groupId}
                value={option.letter}
                checked={selected}
                onChange={() => onChange(option.letter)}
                className="mt-1 size-4 accent-[var(--color-primary)]"
              />
              <span className="flex-1 text-[15px] leading-relaxed text-[var(--color-text)]">
                <span
                  aria-hidden="true"
                  className="mr-2 font-medium text-[var(--color-text-secondary)]"
                >
                  {option.letter}.
                </span>
                {option.text}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function Stimulus({ item }: { readonly item: PlacementItem }) {
  return (
    <>
      {item.passage ? (
        <div className="rounded-[var(--radius-lg)] bg-[var(--color-surface-hover)] p-4 text-[15px] leading-[1.9] text-[var(--color-text)]">
          {item.passage.split("\n").map((line, index) => (
            <p key={index} className={index > 0 ? "mt-2" : undefined}>
              {line}
            </p>
          ))}
        </div>
      ) : null}
      {item.stem ? (
        <p className="text-[16px] leading-relaxed text-[var(--color-text)]">
          {item.stem}
        </p>
      ) : null}
      {item.prompt ? (
        <p className="text-[14px] text-[var(--color-text-secondary)]">
          {item.prompt}
        </p>
      ) : null}
    </>
  );
}

interface SequenceQuestionProps extends PlacementQuestionProps {
  readonly groupId: string;
}

/** Expand a stored order such as `"C-A-B"` into fixed-length position slots. */
function seedSlots(value: string | null, size: number): string[] {
  const parts = value ? value.split("-") : [];
  return Array.from({ length: size }, (_, index) => parts[index] ?? "");
}

/**
 * Whether an order string is a complete, duplicate-free permutation.
 *
 * The sitting uses this to decide what to send: a partial order like `"C--"` is
 * kept on screen so the learner does not lose their work when they page away,
 * but it is not a legal response and is never persisted or counted as answered.
 */
export function isCompleteOrder(value: string | null, size: number): boolean {
  if (!value) return false;
  const parts = value.split("-").filter(Boolean);
  return parts.length === size && new Set(parts).size === size;
}

/**
 * The ordering item: three positions, each a select over the fragments.
 *
 * A fragment already used in another position is disabled rather than hidden,
 * so the list does not reorder under the learner mid-task, and the answer is
 * only sent once all positions are filled: a partial order is not a legal
 * response and the server would reject it.
 *
 * Partial state is held locally rather than derived from `value`. Deriving it
 * loses every intermediate choice, because `value` is null until the order is
 * complete, so picking position 1 and then position 2 would silently discard
 * position 1.
 */
function SequenceQuestion({
  item,
  value,
  onChange,
  groupId,
}: SequenceQuestionProps) {
  const t = useTranslations("placement.sitting");
  const size = item.option_letters.length;

  const [slots, setSlots] = useState<string[]>(() => seedSlots(value, size));

  // Re-seed when the parent hands back a different order, e.g. a resumed
  // attempt restoring a saved answer or the learner paging back to this item.
  // This is React's documented "adjust state during render" pattern: a state
  // mirror rather than a ref, so it is legal to read during render and re-runs
  // the component immediately instead of after a paint.
  const [seededFrom, setSeededFrom] = useState(value);
  if (value !== seededFrom) {
    setSeededFrom(value);
    setSlots(seedSlots(value, size));
  }

  const setPosition = useCallback(
    (index: number, letter: string) => {
      // Computed from the current slots and applied directly, NOT inside a
      // setState updater. An updater runs during React's render phase, so
      // calling the parent's `onChange` from in there is a setState-during-
      // render of a different component -- React warns, and in the sitting it
      // broke the whole answer surface.
      const next = [...slots];
      next[index] = letter;
      setSlots(next);
      // The partial order is reported too. The sitting keeps it on screen but
      // only sends a complete one, so paging away mid-order does not discard
      // the positions already chosen.
      onChange(next.some(Boolean) ? next.join("-") : null);
    },
    [onChange, slots]
  );

  const letters = slots;

  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">
        {t("questionLegend", { number: item.question_number })}
      </legend>

      <Stimulus item={item} />

      {/* Unordered: an <ol> would assert the very sequence the learner is
          being asked to work out. */}
      <ul className="space-y-2">
        {item.options.map((option) => (
          <li
            key={option.letter}
            className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <span
              aria-hidden="true"
              className="font-medium text-[var(--color-text-secondary)]"
            >
              {option.letter}.
            </span>
            <span className="text-[15px] leading-relaxed text-[var(--color-text)]">
              {option.text}
            </span>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-end gap-3">
        {item.option_letters.map((_, index) => {
          const id = `${groupId}-pos-${index}`;
          const current = letters[index] ?? "";
          return (
            <div key={index} className="flex flex-col gap-1">
              <label
                htmlFor={id}
                className="text-[12px] font-medium text-[var(--color-text-secondary)]"
              >
                {t("orderPosition", { position: index + 1 })}
              </label>
              <select
                id={id}
                value={current}
                onChange={(event) => setPosition(index, event.target.value)}
                className="h-11 min-w-20 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-[15px] text-[var(--color-text)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40"
              >
                <option value="">{t("orderEmpty")}</option>
                {item.options.map((option) => (
                  <option
                    key={option.letter}
                    value={option.letter}
                    disabled={
                      current !== option.letter && letters.includes(option.letter)
                    }
                  >
                    {option.letter}. {option.text}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
