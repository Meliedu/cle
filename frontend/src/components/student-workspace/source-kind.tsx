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
 * checklist row or the overview next-action reads its kind at a glance. This is
 * a static module-level map (mirrors `toneStyles`) so the lookup + render stays
 * a static-component pattern, not a component created during render.
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

interface SourceKindIconProps {
  readonly kind: WorkItemSourceKind;
  readonly className?: string;
}

/** Renders the icon for a work-item source kind. Labels stay copy-free. */
export function SourceKindIcon({ kind, className }: SourceKindIconProps) {
  const Icon = SOURCE_ICON[kind];
  return (
    <Icon aria-hidden="true" strokeWidth={1.85} className={className} />
  );
}
