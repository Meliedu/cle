"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { FolderTree, ClipboardCheck, KeyRound, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/patterns";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CourseBasicsFields,
  EMPTY_COURSE_BASICS,
  type CourseBasicsValue,
} from "@/components/course/course-basics-fields";
import { useCreateCourse } from "@/hooks/use-courses";

/**
 * T014 — new-course-start. Entry screen for a teacher to create a course before
 * students join. On success it routes into the setup wizard, where the same
 * basics can be refined (T015). A "Setup creates" aside previews what publishing
 * the wizard will generate.
 *
 * Validation: only the name is required here (consistent with the basics step);
 * code/language/term are recommended-but-optional — the setup checklist, not
 * per-field required attrs, is the real course-open gate.
 */
export default function NewCoursePage() {
  const t = useTranslations("teacher.setup.newCourse");
  const router = useRouter();
  const createCourse = useCreateCourse();

  const [form, setForm] = useState<CourseBasicsValue>(EMPTY_COURSE_BASICS);
  const [nameError, setNameError] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const setField = useCallback(
    (field: keyof CourseBasicsValue, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      if (field === "name") setNameError(false);
    },
    []
  );

  const handleSubmit = useCallback(
    async (event: { preventDefault: () => void }) => {
      event.preventDefault();
      if (!form.name.trim()) {
        setNameError(true);
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

          <CourseBasicsFields
            idPrefix="course"
            value={form}
            onValueChange={setField}
            errors={nameError ? { name: t("nameRequired") } : undefined}
            labels={{
              name: t("name"),
              namePlaceholder: t("namePlaceholder"),
              code: t("code"),
              codePlaceholder: t("codePlaceholder"),
              semester: t("semester"),
              semesterPlaceholder: t("semesterPlaceholder"),
              language: t("language"),
              languagePlaceholder: t("languagePlaceholder"),
              description: t("description"),
              descriptionPlaceholder: t("descriptionPlaceholder"),
              descriptionHint: t("descriptionHint"),
            }}
          />

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
