import { ObjectivesEditor } from "@/components/curriculum/objectives-editor";

export default async function ObjectivesPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Learning Objectives
      </h1>
      <ObjectivesEditor courseId={courseId} />
    </div>
  );
}
