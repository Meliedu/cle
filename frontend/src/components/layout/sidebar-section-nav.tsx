"use client";

import Link from "next/link";
import {
  LayoutDashboard,
  FolderOpen,
  Radio,
  Mic,
  HelpCircle,
  Layers,
  RotateCcw,
  TrendingUp,
  Trophy,
  Users,
  Link2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { CANVAS_ENABLED } from "@/lib/features";

interface SectionItem {
  readonly label: string;
  readonly value: string;
  readonly icon: React.ComponentType<{ className?: string }>;
  readonly instructorOnly?: boolean;
  readonly studentOnly?: boolean;
}

interface SectionGroup {
  readonly label: string;
  readonly items: readonly SectionItem[];
}

const SECTION_GROUPS: readonly SectionGroup[] = [
  {
    label: "",
    items: [
      { label: "Overview", value: "overview", icon: LayoutDashboard },
    ],
  },
  {
    label: "Before Class",
    items: [
      { label: "Materials", value: "materials", icon: FolderOpen },
    ],
  },
  {
    label: "In Class",
    items: [
      { label: "Live Quiz", value: "live", icon: Radio },
    ],
  },
  {
    label: "After Class",
    items: [
      { label: "Quizzes", value: "quizzes", icon: HelpCircle },
      { label: "Flashcards", value: "flashcards", icon: Layers },
      { label: "Revision", value: "revision", icon: RotateCcw, studentOnly: true },
      { label: "Pronunciation", value: "pronunciation", icon: Mic },
    ],
  },
  {
    label: "Insights",
    items: [
      { label: "Progress", value: "progress", icon: TrendingUp, studentOnly: true },
      { label: "Leaderboard", value: "leaderboard", icon: Trophy, studentOnly: true },
      { label: "Students", value: "students", icon: Users, instructorOnly: true },
    ],
  },
  {
    label: "Integrations",
    items: [
      ...(CANVAS_ENABLED
        ? ([{ label: "Canvas", value: "canvas", icon: Link2, instructorOnly: true }] as const)
        : []),
    ],
  },
];

interface SidebarSectionNavProps {
  readonly courseId: string;
  readonly activeTab: string;
  readonly isInstructor: boolean;
  readonly collapsed: boolean;
  readonly onMobileClose?: () => void;
}

export function SidebarSectionNav({
  courseId,
  activeTab,
  isInstructor,
  collapsed,
  onMobileClose,
}: SidebarSectionNavProps) {
  return (
    <div className="space-y-4 px-2">
      {SECTION_GROUPS.map((group) => {
        const visibleItems = group.items.filter((item) => {
          if (item.instructorOnly && !isInstructor) return false;
          if (item.studentOnly && isInstructor) return false;
          return true;
        });
        if (visibleItems.length === 0) return null;

        return (
          <div key={group.label}>
            {!collapsed && (
              <p className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                {group.label}
              </p>
            )}
            <div className="space-y-0.5">
              {visibleItems.map((item) => {
                const isActive = activeTab === item.value;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.value}
                    href={`/dashboard/courses/${courseId}?tab=${item.value}`}
                    onClick={onMobileClose}
                    className={cn(
                      "flex items-center gap-2.5 rounded-[var(--radius-md)] px-2.5 py-1.5 text-sm transition-colors duration-[var(--duration-fast)]",
                      collapsed && "justify-center px-2",
                      isActive
                        ? "bg-[var(--color-primary-light)] font-medium text-[var(--color-primary)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
                    )}
                    title={collapsed ? item.label : undefined}
                  >
                    <Icon className={cn(
                      "size-4 shrink-0",
                      isActive ? "text-[var(--color-primary)]" : "text-[var(--color-text-muted)]"
                    )} />
                    {!collapsed && <span>{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
