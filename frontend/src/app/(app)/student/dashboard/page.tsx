import { StudentHome } from "@/components/dashboard/student-home";

/**
 * `/student/dashboard`: the student global home (Student 01).
 *
 * Owns: the one recoverable next action, the rest of the learning path, and a
 * read-only day rail. Does not own course-local navigation or the sequence
 * itself, which belongs to the course.
 */
export default function StudentDashboardPage() {
  return <StudentHome />;
}
