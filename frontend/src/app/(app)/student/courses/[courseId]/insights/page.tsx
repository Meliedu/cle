import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/patterns";
import { IloStrengthMap } from "@/components/student-insights/ilo-strength-map";
import { SkillPatternMap } from "@/components/student-insights/skill-pattern-map";

interface StudentInsightsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/insights` — S064 ILO strength map + S065 skill
 * pattern map, each wired to its designed no-evidence state (S070). Server
 * component: awaits async `params`, then renders the mobile-first stack. The
 * waiting-for-instructor-feedback state (S071) lives on the signal surface
 * (`SignalDetail`, reused from the follow-up detail).
 */
export default async function StudentInsightsPage({
  params,
}: StudentInsightsPageProps) {
  const { courseId } = await params;
  const t = await getTranslations("student.insights");

  return (
    <div className="mx-auto w-full max-w-2xl space-y-8 py-2">
      <PageHeader
        title={t("title")}
        description={t("subtitle")}
        breadcrumb={
          <Link
            href={`/student/courses/${courseId}`}
            className="hover:text-[var(--color-text)]"
          >
            {t("back")}
          </Link>
        }
        actions={
          <Link
            href={`/student/courses/${courseId}/profile`}
            className="inline-flex min-h-11 items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-[13px] font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
          >
            {t("viewProfile")}
          </Link>
        }
      />

      <IloStrengthMap courseId={courseId} />
      <SkillPatternMap courseId={courseId} />
    </div>
  );
}
