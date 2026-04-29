"use client";
import { useRole } from "@/hooks/use-role";
import { useMyMastery, useCohortMastery } from "@/hooks/use-mastery";
import { ConceptMasteryBar } from "@/components/concepts/concept-mastery-bar";
import { CohortMasteryTable } from "@/components/concepts/cohort-mastery-table";
import { use } from "react";

export default function MasteryPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(props.params);
  const { role } = useRole();

  if (role === "instructor") {
    return <InstructorView courseId={courseId} />;
  }
  return <StudentView courseId={courseId} />;
}

function StudentView({ courseId }: { courseId: string }) {
  const { data, isLoading } = useMyMastery(courseId);
  if (isLoading) return <p>Loading mastery…</p>;
  if (!data || data.length === 0) {
    return <p className="text-sm text-[var(--color-muted)]">
      No mastery yet. Complete a quiz, flashcard review, or speaking practice to start.
    </p>;
  }
  return (
    <div className="mx-auto max-w-2xl space-y-3">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Your Mastery
      </h1>
      {data.map((row) => (
        <ConceptMasteryBar
          key={row.concept_id}
          conceptName={row.concept_name}
          mastery={Number(row.mastery_score)}
          confidence={Number(row.confidence)}
          attempts={row.attempt_count}
        />
      ))}
    </div>
  );
}

function InstructorView({ courseId }: { courseId: string }) {
  const { data, isLoading } = useCohortMastery(courseId);
  if (isLoading) return <p>Loading cohort mastery…</p>;
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Cohort Mastery
      </h1>
      <CohortMasteryTable rows={data ?? []} />
    </div>
  );
}
