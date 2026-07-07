import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { MaterialsLibrary } from "@/components/materials/materials-library";

interface MaterialsPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/materials` — T052–T059 materials library. The
 * ingest + organize surface of the course workspace: upload files, add link
 * resources, browse by session folder, and (F7) preview / assign / remove.
 * Server component: awaits async `params`, then renders the shared workspace
 * shell with the `materials` tab active.
 */
export default async function MaterialsPage({ params }: MaterialsPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="materials">
      <MaterialsLibrary courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
