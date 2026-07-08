import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { PageHeader } from "@/components/patterns";
import { ReportArchive } from "@/components/student-reports";

interface StudentReportsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/reports` — S066 report archive. Server
 * component: awaits async `params`, then renders the mobile-first archive of
 * SENT reports only. A student never sees an unsent/draft report (the read
 * returns `sent` rows only); the not-yet-sent case is the archive's designed
 * waiting shell (S069).
 */
export default async function StudentReportsPage({
  params,
}: StudentReportsPageProps) {
  const { courseId } = await params;
  const t = await getTranslations("student.reports");

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
      />

      <ReportArchive courseId={courseId} />
    </div>
  );
}
