import type { StatusTone } from "@/components/course/session-status";
import type { WorkItemStatus } from "@/hooks/use-work-items";

/**
 * One visual treatment per `work_item_progress.status`, shared by the student
 * overview, checklist, and sessions surfaces (P4 F2–F4). Each status maps to
 * exactly one tone from the shared `StatusChip` palette so the same status
 * always reads the same across screens. Labels stay copy-free (next-intl keys
 * live at `student.checklist.status.*`).
 */
export function workItemTone(status: WorkItemStatus): StatusTone {
  switch (status) {
    case "completed":
      return "success";
    case "submitted":
    case "follow_up_assigned":
      return "info";
    case "in_progress":
    case "late":
      return "progress";
    case "missed":
      return "muted";
    case "pending":
    default:
      return "neutral";
  }
}

/**
 * A checklist item counts as "done" once the student has a terminal positive
 * outcome — completed or submitted. Used to compute overview progress and to
 * split the checklist into open vs done groups.
 */
export function isWorkItemDone(status: WorkItemStatus): boolean {
  return status === "completed" || status === "submitted";
}

/** Grouping bucket for the checklist — open work sorts above done/closed. */
export type ChecklistBucket = "open" | "done" | "missed";

export function checklistBucket(status: WorkItemStatus): ChecklistBucket {
  if (status === "missed") return "missed";
  if (isWorkItemDone(status)) return "done";
  return "open";
}
