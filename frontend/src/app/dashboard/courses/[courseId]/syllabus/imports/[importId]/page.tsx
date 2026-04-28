import { SyllabusPayloadReview } from "@/components/curriculum/syllabus-payload-review";

export default async function SyllabusImportReviewPage(
  props: { params: Promise<{ courseId: string; importId: string }> }
) {
  const { courseId, importId } = await props.params;
  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <SyllabusPayloadReview courseId={courseId} importId={importId} />
    </div>
  );
}
