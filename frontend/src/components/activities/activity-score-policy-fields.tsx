"use client";

import { useTranslations } from "next-intl";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { StateBanner } from "@/components/patterns";
import { useScoreCategories } from "@/hooks/use-setup";
import type { GradingMode, LateRule } from "@/hooks/use-quizzes";

/** The score-policy subset of the builder's form state. */
export interface ScorePolicyValue {
  readonly score_bearing: boolean;
  readonly score_category_id: string | null;
  readonly points: number | null;
  readonly grading_mode: GradingMode | null;
  readonly late_rule: LateRule | null;
  readonly due_at: string | null;
  readonly close_at: string | null;
}

interface ActivityScorePolicyFieldsProps {
  readonly courseId: string;
  readonly value: ScorePolicyValue;
  readonly onChange: (next: ScorePolicyValue) => void;
  /** Field ids the server flagged as missing — highlighted inline. */
  readonly missing?: readonly string[];
}

const GRADING_MODES: readonly GradingMode[] = ["auto", "manual", "participation"];
const LATE_RULES: readonly LateRule[] = [
  "accept_late",
  "reject_late",
  "accept_with_flag",
];

/**
 * The activities-track score-policy panel (F4). A score-bearing toggle reveals
 * the fields the server requires before a score-bearing activity can publish:
 * category, points, grading mode, late rule, and due/close windows. Any field
 * the backend reports in `missing[]` is highlighted so the teacher can jump
 * straight to it after a blocked publish. All updates are immutable.
 */
export function ActivityScorePolicyFields({
  courseId,
  value,
  onChange,
  missing = [],
}: ActivityScorePolicyFieldsProps) {
  const t = useTranslations("teacher.activities.builder.score");
  const categories = useScoreCategories(courseId);
  const isMissing = (field: string): boolean => missing.includes(field);

  const set = <K extends keyof ScorePolicyValue>(
    key: K,
    v: ScorePolicyValue[K]
  ): void => onChange({ ...value, [key]: v });

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
            {t("title")}
          </h3>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("description")}
          </p>
        </div>
        <Switch
          checked={value.score_bearing}
          onCheckedChange={(checked) => set("score_bearing", checked)}
          aria-label={t("toggle")}
        />
      </div>

      {value.score_bearing ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("fields.category")}
            required
            highlighted={isMissing("score_category_id")}
            requiredLabel={t("required")}
          >
            {categories.isError ? (
              <StateBanner
                tone="warning"
                title={t("categoriesError.title")}
                reason={t("categoriesError.reason")}
              />
            ) : (
              <Select
                value={value.score_category_id ?? ""}
                onValueChange={(v) => set("score_category_id", v || null)}
              >
                <SelectTrigger className="w-full" id="activity-score-category">
                  <SelectValue placeholder={t("fields.categoryPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {(categories.data ?? []).map((cat) => (
                    <SelectItem key={cat.id} value={cat.id}>
                      {cat.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </Field>

          <Field
            label={t("fields.points")}
            required
            highlighted={isMissing("points")}
            requiredLabel={t("required")}
          >
            <Input
              type="number"
              min={0}
              inputMode="numeric"
              value={value.points ?? ""}
              onChange={(e) =>
                set("points", e.target.value === "" ? null : Number(e.target.value))
              }
              className="h-9"
            />
          </Field>

          <Field
            label={t("fields.gradingMode")}
            required
            highlighted={isMissing("grading_mode")}
            requiredLabel={t("required")}
          >
            <Select
              value={value.grading_mode ?? ""}
              onValueChange={(v) => set("grading_mode", (v || null) as GradingMode | null)}
            >
              <SelectTrigger className="w-full" id="activity-grading-mode">
                <SelectValue placeholder={t("fields.select")} />
              </SelectTrigger>
              <SelectContent>
                {GRADING_MODES.map((mode) => (
                  <SelectItem key={mode} value={mode}>
                    {t(`gradingModes.${mode}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field
            label={t("fields.lateRule")}
            required
            highlighted={isMissing("late_rule")}
            requiredLabel={t("required")}
          >
            <Select
              value={value.late_rule ?? ""}
              onValueChange={(v) => set("late_rule", (v || null) as LateRule | null)}
            >
              <SelectTrigger className="w-full" id="activity-late-rule">
                <SelectValue placeholder={t("fields.select")} />
              </SelectTrigger>
              <SelectContent>
                {LATE_RULES.map((rule) => (
                  <SelectItem key={rule} value={rule}>
                    {t(`lateRules.${rule}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <Field
            label={t("fields.dueAt")}
            highlighted={isMissing("due_at")}
            requiredLabel={t("required")}
          >
            <Input
              type="datetime-local"
              value={value.due_at ?? ""}
              onChange={(e) => set("due_at", e.target.value || null)}
              className="h-9"
            />
          </Field>

          <Field
            label={t("fields.closeAt")}
            highlighted={isMissing("close_at")}
            requiredLabel={t("required")}
          >
            <Input
              type="datetime-local"
              value={value.close_at ?? ""}
              onChange={(e) => set("close_at", e.target.value || null)}
              className="h-9"
            />
          </Field>
        </div>
      ) : null}
    </section>
  );
}

interface FieldProps {
  readonly label: string;
  readonly required?: boolean;
  readonly highlighted?: boolean;
  readonly requiredLabel: string;
  readonly children: React.ReactNode;
}

function Field({ label, required, highlighted, requiredLabel, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <Label
        className={
          highlighted
            ? "text-[13px] font-medium text-[var(--color-error)]"
            : "text-[13px] font-medium text-[var(--color-text)]"
        }
      >
        {label}
        {required ? (
          <span className="ml-1 text-[var(--color-text-muted)]">
            ({requiredLabel})
          </span>
        ) : null}
      </Label>
      {children}
    </div>
  );
}
