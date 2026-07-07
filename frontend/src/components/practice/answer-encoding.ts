/**
 * Per-type answer encoding for student practice + graded quiz renderers (P5 F7).
 *
 * The backend `grade_question` (B7) decodes exactly these shapes from
 * `answers: {"<question_id>": <string>}`:
 * - `multiple_choice`  → the option KEY string, e.g. `"b"`.
 * - `matching`         → `JSON.stringify({left_id: right_id})`.
 * - `ordering`         → `JSON.stringify([...ids in chosen order])`.
 * - `short_answer`     → the raw typed text (plain string).
 *
 * Storage the builder wrote (for RENDERING): MC `options={key:label}`; matching
 * `options={left:[...],right:[...]}`; ordering `options=items[]`; short_answer
 * `options=null`. `correct_answer` is redacted (null) for students, so these
 * encoders never depend on it. Keeping this pure + framework-free makes the
 * exact wire contract unit-testable in isolation.
 */

export type QuestionType =
  | "multiple_choice"
  | "matching"
  | "ordering"
  | "short_answer";

/** A normalized renderable choice: a stable id plus a human label. */
export interface Choice {
  readonly id: string;
  readonly label: string;
}

/**
 * Per-question draft state. Kept as a discriminated union so the renderer and
 * the encoder agree on shape at compile time. `encodeAnswer` turns each draft
 * into the exact string the backend decodes.
 */
export type AnswerDraft =
  | { readonly type: "multiple_choice"; readonly key: string | null }
  | { readonly type: "matching"; readonly map: Readonly<Record<string, string>> }
  | { readonly type: "ordering"; readonly order: readonly string[] }
  | { readonly type: "short_answer"; readonly text: string };

/** Coerce a free-string `Question.type` to a supported renderer type. */
export function toQuestionType(raw: string | null | undefined): QuestionType {
  switch (raw) {
    case "matching":
    case "ordering":
    case "short_answer":
      return raw;
    default:
      return "multiple_choice";
  }
}

function labelOf(value: unknown, fallback: string): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

/**
 * Normalize a builder payload into `Choice[]`. Defensive by design: the teacher
 * quiz track owns question authoring, so we accept the plausible shapes without
 * modifying their storage — a plain string (id === label), an object with
 * `{id|key|value}` + `{label|text|value}`, or an object map `{key: label}`.
 */
export function normalizeChoiceList(raw: unknown): Choice[] {
  if (Array.isArray(raw)) {
    return raw.map((item, index) => normalizeChoice(item, index));
  }
  if (raw && typeof raw === "object") {
    return Object.entries(raw as Record<string, unknown>).map(([key, value]) => ({
      id: key,
      label: labelOf(value, key),
    }));
  }
  return [];
}

function normalizeChoice(item: unknown, index: number): Choice {
  if (typeof item === "string") return { id: item, label: item };
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>;
    const id = String(record.id ?? record.key ?? record.value ?? index);
    const label = labelOf(
      record.label ?? record.text ?? record.value ?? record.id,
      id
    );
    return { id, label };
  }
  return { id: String(index), label: String(item) };
}

/** Left / right columns for a matching question, normalized from `options`. */
export interface MatchingColumns {
  readonly left: readonly Choice[];
  readonly right: readonly Choice[];
}

export function matchingColumns(options: unknown): MatchingColumns {
  if (options && typeof options === "object" && !Array.isArray(options)) {
    const record = options as Record<string, unknown>;
    return {
      left: normalizeChoiceList(record.left),
      right: normalizeChoiceList(record.right),
    };
  }
  return { left: [], right: [] };
}

/** The initial (empty / natural-order) draft for a question type. */
export function initialDraft(type: QuestionType, options: unknown): AnswerDraft {
  switch (type) {
    case "matching":
      return { type, map: {} };
    case "ordering":
      return {
        type,
        order: normalizeChoiceList(options).map((choice) => choice.id),
      };
    case "short_answer":
      return { type, text: "" };
    default:
      return { type: "multiple_choice", key: null };
  }
}

/**
 * Whether a draft counts as answered for the progress gate. Ordering is always
 * answered once initialized (an order always exists); matching requires every
 * left item mapped; MC / short-answer require a non-empty value.
 */
export function isDraftAnswered(
  draft: AnswerDraft,
  columns?: MatchingColumns
): boolean {
  switch (draft.type) {
    case "multiple_choice":
      return draft.key !== null && draft.key !== "";
    case "short_answer":
      return draft.text.trim() !== "";
    case "ordering":
      return draft.order.length > 0;
    case "matching": {
      const leftCount = columns?.left.length ?? 0;
      if (leftCount === 0) return Object.keys(draft.map).length > 0;
      return columns!.left.every(
        (choice) =>
          typeof draft.map[choice.id] === "string" &&
          draft.map[choice.id] !== ""
      );
    }
  }
}

/**
 * Encode a draft into the exact string the backend `grade_question` decodes.
 * This is the single source of truth for the wire contract.
 */
export function encodeAnswer(draft: AnswerDraft): string {
  switch (draft.type) {
    case "multiple_choice":
      return draft.key ?? "";
    case "short_answer":
      return draft.text;
    case "matching":
      return JSON.stringify(draft.map);
    case "ordering":
      return JSON.stringify(draft.order);
  }
}

/** Move the item at `index` one slot up (−1) or down (+1); pure + immutable. */
export function reorder(
  order: readonly string[],
  index: number,
  direction: -1 | 1
): string[] {
  const target = index + direction;
  if (target < 0 || target >= order.length) return [...order];
  const next = [...order];
  const [moved] = next.splice(index, 1);
  next.splice(target, 0, moved);
  return next;
}
