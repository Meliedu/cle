"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import { useCreateCourse } from "@/hooks/use-courses";
import { useSafeError } from "@/hooks/use-safe-error";

interface CreateCourseDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}

interface FormState {
  readonly name: string;
  readonly code: string;
  readonly language: string;
  readonly semester: string;
  readonly description: string;
}

const initialForm: FormState = {
  name: "",
  code: "",
  language: "",
  semester: "",
  description: "",
};

const languages = ["Chinese", "English", "Japanese", "Korean"] as const;

interface FormErrors {
  readonly name?: string;
  readonly code?: string;
  readonly language?: string;
  readonly semester?: string;
}

/** Validation copy is injected so this stays a pure function AND localised. */
function validateForm(
  form: FormState,
  t: (key: string) => string
): FormErrors {
  const errors: Record<string, string> = {};

  if (!form.name.trim()) {
    errors.name = t("nameRequired");
  }
  if (!form.code.trim()) {
    errors.code = t("codeRequired");
  }
  if (!form.language) {
    errors.language = t("languageRequired");
  }
  if (!form.semester.trim()) {
    errors.semester = t("semesterRequired");
  }

  return errors;
}

export function CreateCourseDialog({
  open,
  onOpenChange,
}: CreateCourseDialogProps) {
  const t = useTranslations("teacher.createCourse");
  const safeError = useSafeError();
  const router = useRouter();
  const createCourse = useCreateCourse();
  const [form, setForm] = useState<FormState>(initialForm);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const isSubmitting = createCourse.isPending;

  const updateField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      // Clear error on change
      setErrors((prev) => {
        if (prev[field as keyof FormErrors]) {
          const next = { ...prev };
          delete next[field as keyof FormErrors];
          return next;
        }
        return prev;
      });
    },
    []
  );

  const handleSubmit = useCallback(
    async (e: { preventDefault: () => void }) => {
      e.preventDefault();
      const validationErrors = validateForm(form, t);

      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors);
        return;
      }

      setSubmitError(null);

      try {
        const course = await createCourse.mutateAsync({
          name: form.name.trim(),
          code: form.code.trim() || null,
          description: form.description.trim() || null,
          language: form.language,
          semester: form.semester.trim() || null,
          settings: {},
        });

        onOpenChange(false);
        setForm(initialForm);
        setErrors({});

        // A new course is `draft`, and the one honest next action for a draft
        // is finishing its setup. Previously this dialog closed and dropped the
        // instructor back on the roster with no indication of what to do next,
        // and the created row was discarded rather than used. `useCreateCourse`
        // returns the persisted course precisely so the caller can route here.
        router.push(`/teacher/courses/${course.id}/setup`);
      } catch (error: unknown) {
        setSubmitError(
          safeError.fromError(error, { objectName: form.name.trim() }).title
        );
      }
    },
    [form, onOpenChange, createCourse, router, t, safeError]
  );

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setForm(initialForm);
        setErrors({});
        setSubmitError(null);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div className="space-y-1.5">
            <Label htmlFor="course-name">
              {t("nameLabel")}{" "}
              <span className="text-[var(--color-error)]" aria-label={t("requiredMark")}>
                *
              </span>
            </Label>
            <Input
              id="course-name"
              placeholder={t("namePlaceholder")}
              value={form.name}
              onChange={(e) => updateField("name", e.target.value)}
              aria-invalid={!!errors.name}
              aria-describedby={errors.name ? "course-name-error" : undefined}
            />
            {errors.name && (
              <p id="course-name-error" className="text-xs text-[var(--color-error)]">
                {errors.name}
              </p>
            )}
          </div>

          {/* Code */}
          <div className="space-y-1.5">
            <Label htmlFor="course-code">
              {t("codeLabel")}{" "}
              <span className="text-[var(--color-error)]" aria-label={t("requiredMark")}>
                *
              </span>
            </Label>
            <Input
              id="course-code"
              placeholder={t("codePlaceholder")}
              value={form.code}
              onChange={(e) => updateField("code", e.target.value)}
              aria-invalid={!!errors.code}
              aria-describedby={errors.code ? "course-code-error" : undefined}
            />
            {errors.code && (
              <p id="course-code-error" className="text-xs text-[var(--color-error)]">
                {errors.code}
              </p>
            )}
          </div>

          {/* Language */}
          <div className="space-y-1.5">
            <Label>
              {t("languageLabel")}{" "}
              <span className="text-[var(--color-error)]" aria-label={t("requiredMark")}>
                *
              </span>
            </Label>
            <Select
              value={form.language}
              onValueChange={(val) => updateField("language", val ?? "")}
            >
              <SelectTrigger
                className="w-full"
                aria-invalid={!!errors.language}
                aria-describedby={errors.language ? "course-language-error" : undefined}
              >
                <SelectValue placeholder={t("languagePlaceholder")} />
              </SelectTrigger>
              <SelectContent>
                {languages.map((lang) => (
                  <SelectItem key={lang} value={lang}>
                    {t(`languages.${lang}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {errors.language && (
              <p id="course-language-error" className="text-xs text-[var(--color-error)]">
                {errors.language}
              </p>
            )}
          </div>

          {/* Semester */}
          <div className="space-y-1.5">
            <Label htmlFor="course-semester">
              {t("semesterLabel")}{" "}
              <span className="text-[var(--color-error)]" aria-label={t("requiredMark")}>
                *
              </span>
            </Label>
            <Input
              id="course-semester"
              placeholder={t("semesterPlaceholder")}
              value={form.semester}
              onChange={(e) => updateField("semester", e.target.value)}
              aria-invalid={!!errors.semester}
              aria-describedby={errors.semester ? "course-semester-error" : undefined}
            />
            {errors.semester && (
              <p id="course-semester-error" className="text-xs text-[var(--color-error)]">
                {errors.semester}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-1.5">
            <Label htmlFor="course-description">{t("descriptionLabel")}</Label>
            <Textarea
              id="course-description"
              placeholder={t("descriptionPlaceholder")}
              value={form.description}
              onChange={(e) => updateField("description", e.target.value)}
              rows={3}
            />
          </div>

          {submitError && (
            <p className="text-sm text-[var(--color-error)]">{submitError}</p>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSubmitting}
            >
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="size-4 animate-spin" />}
              {isSubmitting ? t("submitting") : t("submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
