import { StudentProgress } from "@/components/dashboard/student-progress";

/**
 * `/student/progress` — the "My progress" destination in the student global
 * rail.
 *
 * The rail item existed (STUDENT_GLOBAL_NAV, pinned by nav-config.test.ts) but
 * this route did not, so the fourth item in a student's primary navigation
 * returned a hard 404. Found by scripts/route-sweep.mjs.
 *
 * It answers the one question the rail promises: across every enrolled course,
 * how much of my assigned work is done. It reuses the same cross-course
 * checklist fan-out as Home, so the two can never disagree, and links onward
 * rather than restating what the per-course insights surface already owns.
 */
export default function StudentProgressPage() {
  return <StudentProgress />;
}
