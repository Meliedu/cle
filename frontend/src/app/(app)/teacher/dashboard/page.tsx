import { TeacherHome } from "@/components/dashboard/teacher-home";

/**
 * `/teacher/dashboard`: the teacher global home (Plate 01).
 *
 * Owns: the next teaching action, the later-today agenda, and a compact
 * roster. Does not own course-local navigation or calendar editing.
 */
export default function TeacherDashboardPage() {
  return <TeacherHome />;
}
