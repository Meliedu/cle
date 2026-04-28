import { SyllabusUploadCard } from "@/components/curriculum/syllabus-upload-card";
import { SyllabusImportList } from "@/components/curriculum/syllabus-import-list";

export default async function SyllabusPage(
  props: { params: Promise<{ courseId: string }> }
) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">Syllabus</h1>
      <SyllabusUploadCard courseId={courseId} />
      <SyllabusImportList courseId={courseId} />
    </div>
  );
}
