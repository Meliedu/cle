import { CourseWorkspaceShell } from "@/components/course/course-workspace-shell";
import { CourseMemoryView } from "@/components/memory";

interface MemoryPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * `/teacher/courses/{courseId}/memory` — the T086–T087 course-memory workspace.
 * F1 flipped the `memory` tab enabled + added this route shell; F5 fills the
 * body with the real `CourseMemoryView` (`useMemory` — kind-grouped list +
 * item detail with audited decide controls + next-term suggestions). Server
 * component: awaits async `params`, then renders the shared workspace shell with
 * the `memory` tab active.
 */
export default async function MemoryPage({ params }: MemoryPageProps) {
  const { courseId } = await params;
  return (
    <CourseWorkspaceShell courseId={courseId} activeTab="memory">
      <CourseMemoryView courseId={courseId} />
    </CourseWorkspaceShell>
  );
}
