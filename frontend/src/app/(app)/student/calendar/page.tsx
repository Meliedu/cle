import { Suspense } from "react";

import { CalendarView } from "@/components/dashboard/calendar-view";

/**
 * The single temporal authority for the student lane (Plate 03).
 *
 * Owns month/week state, event filters, and the selected-day agenda, all in
 * URL state, so no other surface holds an independent copy. The Suspense
 * boundary is required because that state is read from the query string.
 */
export default function StudentCalendarPage() {
  return (
    <Suspense fallback={null}>
      <CalendarView />
    </Suspense>
  );
}
