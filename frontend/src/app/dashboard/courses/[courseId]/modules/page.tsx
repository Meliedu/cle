import { ModuleTreeEditor } from "@/components/curriculum/module-tree-editor";

export default async function ModulesPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">Modules</h1>
      <ModuleTreeEditor courseId={courseId} />
    </div>
  );
}
