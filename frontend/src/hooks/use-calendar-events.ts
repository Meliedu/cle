"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch, type ApiEnvelope } from "@/lib/api";
import type { CalendarEvent } from "@/lib/curriculum-types";

export type { CalendarEvent };

export function useCalendarEvents(
  courseId: string,
  fromDate: Date,
  toDate: Date
) {
  const { getToken } = useAuth();
  return useQuery({
    queryKey: [
      "calendar",
      courseId,
      fromDate.toISOString(),
      toDate.toISOString(),
    ],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const params = new URLSearchParams({
        from_date: fromDate.toISOString(),
        to_date: toDate.toISOString(),
      });
      const res = await apiFetch<ApiEnvelope<CalendarEvent[]>>(
        `/courses/${courseId}/calendar?${params}`,
        { token }
      );
      return res.data;
    },
  });
}
