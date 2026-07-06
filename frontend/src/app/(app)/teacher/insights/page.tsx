import { EmptyState, PageHeader } from "@/components/patterns";

export default function TeacherInsightsPage() {
  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6 px-6 py-6 md:px-10 md:py-10">
      <PageHeader title="Insights" />

      <EmptyState
        variant="waiting"
        title="No evidence yet"
        reason="Insights appear here once students start completing course work — quizzes, flashcards, and pronunciation practice all feed the picture of what your class has mastered."
      />
    </div>
  );
}
