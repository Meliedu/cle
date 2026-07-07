import { PageHeader } from "@/components/patterns";
import { TeacherInsightsBrowser } from "@/components/teacher-insights";

/**
 * `/teacher/insights` — the cross-course insights entry point (F5). A course
 * selector drives the shared `CourseInsightsView`: cohort mastery summary,
 * open-alert severity counts, review-queue depth, and a reviewable-signals
 * list opening the T077 signal detail drawer. A genuinely evidence-free course
 * keeps the designed empty state (handled inside the view).
 */
export default function TeacherInsightsPage() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:px-10 md:py-10">
      <PageHeader title="Insights" />
      <TeacherInsightsBrowser />
    </div>
  );
}
