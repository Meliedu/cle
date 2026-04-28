import Link from "next/link";
import { AssignmentDetail } from "@/components/curriculum/assignment-detail";

export default async function AssignmentDetailPage(props: {
  params: Promise<{ courseId: string; assignmentId: string }>;
}) {
  const { courseId, assignmentId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
        <Link
          href={`/dashboard/courses/${courseId}/assignments`}
          className="hover:text-[var(--color-primary)] hover:underline"
        >
          Assignments
        </Link>
        <span>/</span>
        <span className="text-[var(--color-text)]">Detail</span>
      </div>
      <AssignmentDetail courseId={courseId} assignmentId={assignmentId} />
    </div>
  );
}
