import { AssignmentsRouter } from "@/components/curriculum/assignments-router";

export default async function AssignmentsPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Assignments
      </h1>
      <AssignmentsRouter courseId={courseId} />
    </div>
  );
}
