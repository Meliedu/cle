"use client";

import { useTranslations } from "next-intl";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useScoreCategories } from "@/hooks/use-setup";
import type { GradingMode, LateRule } from "@/hooks/use-quizzes";

/** The four gated fields (backend `SCORE_POLICY_INCOMPLETE.missing[]`). */
export type ScorePolicyField =
  | "score_category_id"
  | "points"
  | "grading_mode"
  | "deadline";

/** DOM id for a policy field, so the blocked banner can jump/scroll to it. */
export function policyFieldId(field: ScorePolicyField): string {
  return `score-policy-${field}`;
}

/** Controlled form value — strings so empty maps cleanly to "missing". */
export interface ScorePolicyValue {
  readonly score_category_id: string;
  readonly points: string;
  readonly grading_mode: GradingMode | "";
  readonly late_rule: LateRule | "";
  readonly due_at: string;
  readonly close_at: string;
}

export const EMPTY_SCORE_POLICY: ScorePolicyValue = {
  score_category_id: "",
  points: "",
  grading_mode: "",
  late_rule: "",
  due_at: "",
  close_at: "",
};

const GRADING_MODES: readonly GradingMode[] = ["auto", "manual", "participation"];
const LATE_RULES: readonly LateRule[] = [
  "accept_late",
  "reject_late",
  "accept_with_flag",
];

interface ScorePolicyPanelProps {
  readonly courseId: string;
  readonly value: ScorePolicyValue;
  readonly onChange: (next: ScorePolicyValue) => void;
  /** Fields the publish gate flagged as missing — highlighted for the teacher. */
  readonly missing?: ReadonlySet<ScorePolicyField>;
  readonly disabled?: boolean;
}

/**
 * T067 — the graded-quiz score-policy panel. Collects the four gated fields
 * (`score_category_id`, `points`, `grading_mode`, and a deadline) plus the late
 * rule. The category dropdown reads the course's score categories
 * (`useScoreCategories`, P1). Every field carries a stable DOM id
 * (`policyFieldId`) so the blocked banner can focus it when publish is gated
 * (Decision 7, mirrors P1's `SetupMissingSourceError`). Purely controlled — the
 * publish panel owns persistence.
 */
export function ScorePolicyPanel({
  courseId,
  value,
  onChange,
  missing,
  disabled,
}: ScorePolicyPanelProps) {
  const t = useTranslations("teacher.quiz.policy");
  const { data: categories } = useScoreCategories(courseId);

  const set = <K extends keyof ScorePolicyValue>(
    key: K,
    next: ScorePolicyValue[K]
  ) => onChange({ ...value, [key]: next });

  const flagged = (field: ScorePolicyField) =>
    missing?.has(field) ? "ring-2 ring-[var(--color-error)]/60" : "";

  const deadlineFlagged = missing?.has("deadline");

  return (
    <div className="space-y-4">
      <FieldShell
        id={policyFieldId("score_category_id")}
        label={t("category.label")}
        hint={t("category.hint")}
        flagged={Boolean(missing?.has("score_category_id"))}
      >
        <Select
          value={value.score_category_id || undefined}
          onValueChange={(v) => set("score_category_id", v ?? "")}
          disabled={disabled}
        >
          <SelectTrigger
            id={policyFieldId("score_category_id")}
            className={`w-full ${flagged("score_category_id")}`}
          >
            <SelectValue placeholder={t("category.placeholder")} />
          </SelectTrigger>
          <SelectContent>
            {(categories ?? []).map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FieldShell>

      <div className="grid grid-cols-2 gap-3">
        <FieldShell
          id={policyFieldId("points")}
          label={t("points.label")}
          flagged={Boolean(missing?.has("points"))}
        >
          <Input
            id={policyFieldId("points")}
            type="number"
            min={0}
            inputMode="decimal"
            placeholder={t("points.placeholder")}
            value={value.points}
            disabled={disabled}
            className={flagged("points")}
            onChange={(e) => set("points", e.target.value)}
          />
        </FieldShell>

        <FieldShell
          id={policyFieldId("grading_mode")}
          label={t("grading.label")}
          flagged={Boolean(missing?.has("grading_mode"))}
        >
          <Select
            value={value.grading_mode || undefined}
            onValueChange={(v) => set("grading_mode", (v ?? "") as GradingMode)}
            disabled={disabled}
          >
            <SelectTrigger
              id={policyFieldId("grading_mode")}
              className={`w-full ${flagged("grading_mode")}`}
            >
              <SelectValue placeholder={t("grading.placeholder")} />
            </SelectTrigger>
            <SelectContent>
              {GRADING_MODES.map((m) => (
                <SelectItem key={m} value={m}>
                  {t(`grading.mode.${m}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>
      </div>

      <fieldset
        id={policyFieldId("deadline")}
        className={`space-y-3 rounded-[var(--radius-md)] border p-3 ${
          deadlineFlagged
            ? "border-[var(--color-error)]/60 bg-[var(--color-error-light)]"
            : "border-[var(--color-border)]"
        }`}
      >
        <legend className="px-1 text-[12px] font-medium text-[var(--color-text)]">
          {t("deadline.label")}
        </legend>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor={`${policyFieldId("deadline")}-due`}>
              {t("deadline.due")}
            </Label>
            <Input
              id={`${policyFieldId("deadline")}-due`}
              type="datetime-local"
              value={value.due_at}
              disabled={disabled}
              onChange={(e) => set("due_at", e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`${policyFieldId("deadline")}-close`}>
              {t("deadline.close")}
            </Label>
            <Input
              id={`${policyFieldId("deadline")}-close`}
              type="datetime-local"
              value={value.close_at}
              disabled={disabled}
              onChange={(e) => set("close_at", e.target.value)}
            />
          </div>
        </div>
        <p className="text-[11px] leading-snug text-[var(--color-text-muted)]">
          {t("deadline.hint")}
        </p>
      </fieldset>

      <FieldShell
        id={`${policyFieldId("deadline")}-late`}
        label={t("late.label")}
        hint={t("late.hint")}
        flagged={false}
      >
        <Select
          value={value.late_rule || undefined}
          onValueChange={(v) => set("late_rule", (v ?? "") as LateRule)}
          disabled={disabled}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder={t("late.placeholder")} />
          </SelectTrigger>
          <SelectContent>
            {LATE_RULES.map((r) => (
              <SelectItem key={r} value={r}>
                {t(`late.rule.${r}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FieldShell>
    </div>
  );
}

interface FieldShellProps {
  readonly id: string;
  readonly label: string;
  readonly hint?: string;
  readonly flagged: boolean;
  readonly children: React.ReactNode;
}

function FieldShell({ label, hint, flagged, children }: FieldShellProps) {
  return (
    <div className="space-y-1.5">
      <Label className={flagged ? "text-[var(--color-error)]" : undefined}>
        {label}
      </Label>
      {children}
      {hint ? (
        <p className="text-[11px] leading-snug text-[var(--color-text-muted)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
