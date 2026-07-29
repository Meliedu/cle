import { Suspense } from "react";

import { TeacherRosterView } from "@/components/dashboard/teacher-roster-view";

/**
 * `/teacher/courses`: the operational teaching roster (Plate 02).
 *
 * Owns: search, term/lifecycle filters, and next-class ordering. Does not own
 * session management, which stays inside a course.
 *
 * `Suspense` is required because the view reads `useSearchParams` for its
 * URL-backed filter state.
 */
export default function TeacherCoursesPage() {
  return (
    <Suspense fallback={null}>
      <TeacherRosterView />
    </Suspense>
  );
}
