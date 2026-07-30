import { PlacementReviewQueue } from "@/components/placement/placement-review-queue";

/**
 * `/teacher/placement` — the CLE placement review queue.
 *
 * Global rather than course-scoped: placement decides which course a learner
 * enters, so it cannot live under a course they have not joined.
 */
export default function TeacherPlacementPage() {
  return <PlacementReviewQueue />;
}
