import { StudentCourseShell } from "@/components/student-workspace/student-course-shell";
import { StudentMaterials } from "@/components/student-workspace/student-materials";

interface StudentMaterialsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/student/courses/{courseId}/materials` — S029 materials list + S030 reader.
 * Server component: awaits async `params`, then renders the shared shell +
 * materials library.
 */
export default async function StudentMaterialsPage({
  params,
}: StudentMaterialsPageProps) {
  const { courseId } = await params;
  return (
    <StudentCourseShell courseId={courseId} activeTab="materials">
      <StudentMaterials courseId={courseId} />
    </StudentCourseShell>
  );
}
