import {
  BookOpen,
  ClipboardCheck,
  Dumbbell,
  FileText,
  ListChecks,
  RotateCcw,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import type { WorkItemSourceKind } from "@/hooks/use-work-items";

/**
 * Icon per work-item `source_kind` (spec §4.6 enum). One glyph per source so a
 * checklist row or the overview next-action reads its kind at a glance. Labels
 * are copy-free — next-intl keys live at `student.checklist.kind.*`.
 */
const SOURCE_ICON: Record<WorkItemSourceKind, LucideIcon> = {
  checkpoint: ClipboardCheck,
  practice: Dumbbell,
  quiz: ListChecks,
  activity: Sparkles,
  material: FileText,
  follow_up: RotateCcw,
  report: BookOpen,
};

export function sourceKindIcon(kind: WorkItemSourceKind): LucideIcon {
  return SOURCE_ICON[kind] ?? FileText;
}
