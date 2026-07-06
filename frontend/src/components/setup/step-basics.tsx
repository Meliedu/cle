"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CourseBasicsFields,
  type CourseBasicsValue,
} from "@/components/course/course-basics-fields";
import {
  useCourse,
  useUpdateCourse,
  type CourseResponse,
} from "@/hooks/use-courses";
import { useSetStep } from "@/hooks/use-setup";

interface StepBasicsProps {
  readonly courseId: string;
  /** Fired after basics is saved and its checklist flag is set. */
  readonly onComplete?: () => void;
}

/**
 * T015 — course-basics step. Loads the course, then delegates to a keyed inner
 * form so its state is initialized directly from the loaded course (no
 * setState-in-effect hydration).
 */
export function StepBasics({ courseId, onComplete }: StepBasicsProps) {
  const { data: course, isLoading } = useCourse(courseId);

  if (isLoading || !course) {
    return <StepBasicsSkeleton />;
  }

  return (
    <BasicsForm
      key={course.id}
      courseId={courseId}
      course={course}
      onComplete={onComplete}
    />
  );
}

interface BasicsFormProps {
  readonly courseId: string;
  readonly course: CourseResponse;
  readonly onComplete?: () => void;
}

function BasicsForm({ courseId, course, onComplete }: BasicsFormProps) {
  const t = useTranslations("teacher.setup.basics");
  const updateCourse = useUpdateCourse(courseId);
  const setStep = useSetStep(courseId);

  const [form, setForm] = useState<CourseBasicsValue>({
    name: course.name ?? "",
    code: course.code ?? "",
    language: course.language ?? "",
    semester: course.semester ?? "",
    description: course.description ?? "",
  });
  const [nameError, setNameError] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const setField = useCallback(
    (field: keyof CourseBasicsValue, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }));
      if (field === "name") setNameError(false);
    },
    []
  );

  const handleSave = useCallback(async () => {
    if (!form.name.trim()) {
      setNameError(true);
      return;
    }
    setSaveError(null);
    try {
      await updateCourse.mutateAsync({
        name: form.name.trim(),
        code: form.code.trim() || null,
        description: form.description.trim() || null,
        language: form.language,
        semester: form.semester.trim() || null,
      });
      await setStep.mutateAsync({ step: "basics", done: true });
      onComplete?.();
    } catch {
      setSaveError(t("saveError"));
    }
  }, [form, updateCourse, setStep, onComplete, t]);

  const isSaving = updateCourse.isPending || setStep.isPending;
  const initials = (form.code || form.name || "?").slice(0, 2).toUpperCase();

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-start">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void handleSave();
        }}
        noValidate
        className="space-y-6"
      >
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>

        <CourseBasicsFields
          idPrefix="basics"
          value={form}
          onValueChange={setField}
          errors={nameError ? { name: t("nameRequired") } : undefined}
          labels={{
            name: t("name"),
            code: t("code"),
            semester: t("semester"),
            language: t("language"),
            languagePlaceholder: t("languagePlaceholder"),
            description: t("description"),
            descriptionPlaceholder: t("descriptionPlaceholder"),
            descriptionHint: t("descriptionHint"),
          }}
        />

        {saveError ? (
          <p role="alert" className="text-[13px] text-[var(--color-error)]">
            {saveError}
          </p>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="submit" size="lg" disabled={isSaving}>
            {isSaving ? <Loader2 className="animate-spin" /> : null}
            {isSaving ? t("saving") : t("save")}
          </Button>
        </div>
      </form>

      <aside className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <p className="text-[13px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {t("preview.title")}
        </p>
        <div className="mt-4 flex gap-3">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[15px] font-semibold text-[var(--color-primary-hover)]">
            {initials}
          </span>
          <div className="min-w-0 space-y-0.5">
            <span className="block truncate text-[14px] font-medium text-[var(--color-text)]">
              {form.code || t("preview.untitledCode")}
            </span>
            <span className="block truncate text-[13px] text-[var(--color-text-secondary)]">
              {form.name || t("preview.untitledName")}
            </span>
            <span className="block truncate text-[12px] text-[var(--color-text-muted)]">
              {[form.language, form.semester].filter(Boolean).join(" · ") || "—"}
            </span>
          </div>
        </div>
        <div className="mt-4 flex gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)]/70 bg-[var(--color-surface-hover)] px-3 py-2.5">
          <Lock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-[var(--color-text-muted)]" strokeWidth={1.85} />
          <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("preview.secretsNote")}
          </p>
        </div>
      </aside>
    </div>
  );
}

function StepBasicsSkeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_16rem] lg:items-start">
      <div className="space-y-6">
        <Skeleton className="h-5 w-40" />
        <div className="grid gap-5 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-[var(--radius-lg)]" />
          ))}
        </div>
        <Skeleton className="h-24 rounded-[var(--radius-lg)]" />
        <Skeleton className="h-9 w-40 rounded-[var(--radius-md)]" />
      </div>
      <Skeleton className="h-40 rounded-[var(--radius-xl)]" />
    </div>
  );
}
