import { StudentSubmissionForm } from "@/components/curriculum/student-submission-form";

export default async function SubmitPage(props: {
  params: Promise<{ courseId: string; assignmentId: string }>;
}) {
  const { courseId, assignmentId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Submit Assignment
      </h1>
      <StudentSubmissionForm courseId={courseId} assignmentId={assignmentId} />
    </div>
  );
}
