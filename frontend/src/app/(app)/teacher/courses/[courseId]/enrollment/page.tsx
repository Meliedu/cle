import { permanentRedirect } from "next/navigation";

interface CourseEnrollmentPageProps {
  /** Next.js 16: dynamic route params are async and must be awaited. */
  readonly params: Promise<{ courseId: string }>;
}

/**
 * Alias for the approved Students destination.
 *
 * The migration constraint keeps existing links working while the UI exposes
 * only the approved navigation model: "Do not delete or rename server routes
 * until deep links, redirects, authorization, and analytics have a signed
 * mapping." Enrollment is no longer a navigable destination; it redirects to
 * `/students`, which owns roster, join requests, and course access.
 */
export default async function CourseEnrollmentPage({
  params,
}: CourseEnrollmentPageProps) {
  const { courseId } = await params;
  permanentRedirect(`/teacher/courses/${courseId}/students`);
}
