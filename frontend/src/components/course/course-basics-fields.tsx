"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/** Languages offered for a course. Single source of truth for every basics form. */
export const LANGUAGES = ["Chinese", "English", "Japanese", "Korean"] as const;

/** Controlled value shape shared by the create-course and setup-basics forms. */
export interface CourseBasicsValue {
  readonly name: string;
  readonly code: string;
  readonly language: string;
  readonly semester: string;
  readonly description: string;
}

/** A blank basics value — handy as `useState` seed for the create flow. */
export const EMPTY_COURSE_BASICS: CourseBasicsValue = {
  name: "",
  code: "",
  language: "",
  semester: "",
  description: "",
};

/**
 * Localized strings for the fields. Callers pass these from their own i18n
 * namespace so the presentational component stays translation-agnostic.
 * Placeholders are optional — omit them where a form shows none.
 */
export interface CourseBasicsLabels {
  readonly name: string;
  readonly code: string;
  readonly language: string;
  readonly semester: string;
  readonly description: string;
  readonly languagePlaceholder: string;
  readonly namePlaceholder?: string;
  readonly codePlaceholder?: string;
  readonly semesterPlaceholder?: string;
  readonly descriptionPlaceholder?: string;
  readonly descriptionHint?: string;
}

export interface CourseBasicsFieldsProps {
  /** Namespaces the field ids (e.g. `course` → `course-name`). Must be unique per mounted form. */
  readonly idPrefix: string;
  readonly value: CourseBasicsValue;
  readonly labels: CourseBasicsLabels;
  /** Called with the changed field key and its new string value. */
  readonly onValueChange: (field: keyof CourseBasicsValue, value: string) => void;
  /**
   * Optional per-field error messages. Only `name` is validated as required
   * across the app; other fields are recommended-but-optional (the setup
   * checklist is the real gate), but any field may surface a message here.
   */
  readonly errors?: Partial<Record<keyof CourseBasicsValue, string>>;
  readonly disabled?: boolean;
}

/**
 * Shared, controlled presentation of the core course fields — name, code, term,
 * language, and description. Rendered inside the caller's own `<form>`; it emits
 * a grid of the four short fields plus a full-width description block. Only
 * `name` carries a required marker (see `errors` doc).
 */
export function CourseBasicsFields({
  idPrefix,
  value,
  labels,
  onValueChange,
  errors,
  disabled,
}: CourseBasicsFieldsProps) {
  return (
    <>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          id={`${idPrefix}-name`}
          label={labels.name}
          required
          error={errors?.name}
        >
          <Input
            id={`${idPrefix}-name`}
            placeholder={labels.namePlaceholder}
            value={value.name}
            disabled={disabled}
            onChange={(e) => onValueChange("name", e.target.value)}
            aria-invalid={Boolean(errors?.name) || undefined}
            aria-describedby={errors?.name ? `${idPrefix}-name-error` : undefined}
          />
        </Field>

        <Field id={`${idPrefix}-code`} label={labels.code} error={errors?.code}>
          <Input
            id={`${idPrefix}-code`}
            placeholder={labels.codePlaceholder}
            value={value.code}
            disabled={disabled}
            onChange={(e) => onValueChange("code", e.target.value)}
            aria-invalid={Boolean(errors?.code) || undefined}
          />
        </Field>

        <Field
          id={`${idPrefix}-semester`}
          label={labels.semester}
          error={errors?.semester}
        >
          <Input
            id={`${idPrefix}-semester`}
            placeholder={labels.semesterPlaceholder}
            value={value.semester}
            disabled={disabled}
            onChange={(e) => onValueChange("semester", e.target.value)}
            aria-invalid={Boolean(errors?.semester) || undefined}
          />
        </Field>

        <Field
          id={`${idPrefix}-language`}
          label={labels.language}
          error={errors?.language}
        >
          <Select
            value={value.language}
            onValueChange={(val) => onValueChange("language", val ?? "")}
          >
            <SelectTrigger
              id={`${idPrefix}-language`}
              className="w-full"
              disabled={disabled}
              aria-invalid={Boolean(errors?.language) || undefined}
            >
              <SelectValue placeholder={labels.languagePlaceholder} />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGES.map((lang) => (
                <SelectItem key={lang} value={lang}>
                  {lang}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      </div>

      <Field
        id={`${idPrefix}-description`}
        label={labels.description}
        hint={labels.descriptionHint}
      >
        <Textarea
          id={`${idPrefix}-description`}
          rows={3}
          placeholder={labels.descriptionPlaceholder}
          value={value.description}
          disabled={disabled}
          onChange={(e) => onValueChange("description", e.target.value)}
        />
      </Field>
    </>
  );
}

interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly required?: boolean;
  readonly hint?: string;
  readonly error?: string;
  readonly children: React.ReactNode;
}

function Field({ id, label, required, hint, error, children }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>
        {label}
        {required ? <span className="ml-0.5 text-[var(--color-error)]">*</span> : null}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-[12px] text-[var(--color-error)]">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[12px] text-[var(--color-text-muted)]">{hint}</p>
      ) : null}
    </div>
  );
}
