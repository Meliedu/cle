"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { FolderTree, ClipboardCheck, KeyRound, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/patterns";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
import { useCreateCourse } from "@/hooks/use-courses";

const LANGUAGES = ["Chinese", "English", "Japanese", "Korean"] as const;

interface FormState {
  readonly name: string;
  readonly code: string;
  readonly language: string;
  readonly semester: string;
  readonly description: string;
}

const INITIAL_FORM: FormState = {
  name: "",
  code: "",
  language: "",
  semester: "",
  description: "",
};

type FieldErrors = Partial<Record<"name" | "code" | "language" | "semester", boolean>>;

function validate(form: FormState): FieldErrors {
  return {
    name: !form.name.trim(),
    code: !form.code.trim(),
    language: !form.language,
    semester: !form.semester.trim(),
  };
}

function hasErrors(errors: FieldErrors): boolean {
  return Object.values(errors).some(Boolean);
}

/**
 * T014 — new-course-start. Entry screen for a teacher to create a course before
 * students join. On success it routes into the setup wizard, where the same
 * basics can be refined (T015). A "Setup creates" aside previews what publishing
 * the wizard will generate.
 */
export default function NewCoursePage() {
  const t = useTranslations("teacher.setup.newCourse");
  const router = useRouter();
  const createCourse = useCreateCourse();

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);

  const setField = useCallback(
    <K extends keyof FormState>(field: K, value: FormState[K]) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      setErrors((prev) => (prev[field as keyof FieldErrors] ? { ...prev, [field]: false } : prev));
    },
    []
  );

  const handleSubmit = useCallback(
    async (event: { preventDefault: () => void }) => {
      event.preventDefault();
      const nextErrors = validate(form);
      if (hasErrors(nextErrors)) {
        setErrors(nextErrors);
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
        });
        router.push(`/teacher/courses/${course.id}/setup`);
      } catch {
        setSubmitError(t("createError"));
      }
    },
    [form, createCourse, router, t]
  );

  const isSubmitting = createCourse.isPending;

  const creates = [
    { key: "sessions", Icon: FolderTree },
    { key: "checkpoints", Icon: ClipboardCheck },
    { key: "joinCode", Icon: KeyRound },
  ] as const;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        breadcrumb={
          <Link
            href="/teacher/courses"
            className="rounded-[var(--radius-sm)] transition-colors hover:text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            {t("breadcrumb")}
          </Link>
        }
      />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem] lg:items-start">
        <form onSubmit={handleSubmit} noValidate className="space-y-6">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("sectionTitle")}
          </h2>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field
              id="course-name"
              label={t("name")}
              required
              error={errors.name ? t("nameRequired") : undefined}
            >
              <Input
                id="course-name"
                placeholder={t("namePlaceholder")}
                value={form.name}
                onChange={(e) => setField("name", e.target.value)}
                aria-invalid={errors.name || undefined}
              />
            </Field>

            <Field
              id="course-code"
              label={t("code")}
              required
              error={errors.code ? t("codeRequired") : undefined}
            >
              <Input
                id="course-code"
                placeholder={t("codePlaceholder")}
                value={form.code}
                onChange={(e) => setField("code", e.target.value)}
                aria-invalid={errors.code || undefined}
              />
            </Field>

            <Field
              id="course-semester"
              label={t("semester")}
              required
              error={errors.semester ? t("semesterRequired") : undefined}
            >
              <Input
                id="course-semester"
                placeholder={t("semesterPlaceholder")}
                value={form.semester}
                onChange={(e) => setField("semester", e.target.value)}
                aria-invalid={errors.semester || undefined}
              />
            </Field>

            <Field
              id="course-language"
              label={t("language")}
              required
              error={errors.language ? t("languageRequired") : undefined}
            >
              <Select
                value={form.language}
                onValueChange={(val) => setField("language", val ?? "")}
              >
                <SelectTrigger
                  id="course-language"
                  className="w-full"
                  aria-invalid={errors.language || undefined}
                >
                  <SelectValue placeholder={t("languagePlaceholder")} />
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

          <Field id="course-description" label={t("description")} hint={t("descriptionHint")}>
            <Textarea
              id="course-description"
              rows={3}
              placeholder={t("descriptionPlaceholder")}
              value={form.description}
              onChange={(e) => setField("description", e.target.value)}
            />
          </Field>

          {submitError ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {submitError}
            </p>
          ) : null}

          <div className="flex items-center gap-3 border-t border-[var(--color-border)]/70 pt-5">
            <Button type="submit" size="lg" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="animate-spin" /> : null}
              {isSubmitting ? t("creating") : t("submit")}
            </Button>
            <Link
              href="/teacher/courses"
              className={cn(
                buttonVariants({ variant: "ghost", size: "lg" }),
                isSubmitting && "pointer-events-none opacity-50"
              )}
              aria-disabled={isSubmitting || undefined}
            >
              {t("cancel")}
            </Link>
          </div>
        </form>

        <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
          <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {t("sidebar.title")}
          </p>
          <ul className="mt-4 space-y-4">
            {creates.map(({ key, Icon }) => (
              <li key={key} className="flex gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)]">
                  <Icon aria-hidden="true" className="size-[18px]" strokeWidth={1.85} />
                </span>
                <span className="space-y-0.5">
                  <span className="block text-[14px] font-medium text-[var(--color-text)]">
                    {t(`sidebar.${key}.title`)}
                  </span>
                  <span className="block text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                    {t(`sidebar.${key}.description`)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
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
