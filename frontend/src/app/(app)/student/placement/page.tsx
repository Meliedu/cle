import { PlacementFlow } from "@/components/placement/placement-flow";

/**
 * `/student/placement` — the Chinese placement screener.
 *
 * Standalone rather than a step inside the join funnel. Placement is
 * pre-enrolment and decides which course a learner may join, so nesting it
 * under a course the learner has not been placed into would invert the
 * dependency. The funnel links here instead.
 */
export default function StudentPlacementPage() {
  return <PlacementFlow />;
}
