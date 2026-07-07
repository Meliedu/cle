import Link from "next/link";

import { PageHeader } from "@/components/patterns";
import { LearningProfileView } from "@/components/student-insights/learning-profile";
import { getTranslations } from "next-intl/server";

interface LearningProfilePageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/profile` — S062 learning profile (spec §3.3) over
 * `useLearningProfile`. Server component: awaits async `params`, then renders the
 * mobile-first single-column profile. Standalone page (not the workspace shell)
 * so the student lane can diverge without touching the shared shell.
 */
export default async function LearningProfilePage({
  params,
}: LearningProfilePageProps) {
  const { courseId } = await params;
  const t = await getTranslations("student.profile");

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6 py-2">
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
            href={`/student/courses/${courseId}/insights`}
            className="inline-flex min-h-11 items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-[13px] font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)]"
          >
            {t("viewInsights")}
          </Link>
        }
      />
      <LearningProfileView courseId={courseId} />
    </div>
  );
}
