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
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { CANVAS_ENABLED } from "@/lib/features";

type SectionNavVariant = "light" | "dark";

interface SectionItem {
  readonly label: string;
  readonly value: string;
  readonly icon: LucideIcon;
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
    items: [{ label: "Overview", value: "overview", icon: LayoutDashboard }],
  },
  {
    label: "Before Class",
    items: [{ label: "Materials", value: "materials", icon: FolderOpen }],
  },
  {
    label: "In Class",
    items: [{ label: "Live Quiz", value: "live", icon: Radio }],
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
  readonly variant?: SectionNavVariant;
  readonly onMobileClose?: () => void;
}

export function SidebarSectionNav({
  courseId,
  activeTab,
  isInstructor,
  collapsed,
  variant = "light",
  onMobileClose,
}: SidebarSectionNavProps) {
  const dark = variant === "dark";

  return (
    <div
      className={cn(
        "space-y-5",
        collapsed ? "px-2" : "pl-3 pr-1.5"
      )}
    >
      {SECTION_GROUPS.map((group, groupIndex) => {
        const visibleItems = group.items.filter((item) => {
          if (item.instructorOnly && !isInstructor) return false;
          if (item.studentOnly && isInstructor) return false;
          return true;
        });
        if (visibleItems.length === 0) return null;

        const key = group.label || `group-${groupIndex}`;

        return (
          <div key={key} className="space-y-1.5">
            {!collapsed && group.label ? (
              <p
                className={cn(
                  "px-3 text-[11px] font-semibold uppercase tracking-[0.16em]",
                  dark
                    ? "text-[var(--color-rail-text-muted)]"
                    : "text-[var(--color-text-muted)]"
                )}
              >
                {group.label}
              </p>
            ) : null}
            {/* Thin divider between collapsed groups for visual separation */}
            {collapsed && groupIndex > 0 ? (
              <div
                className={cn(
                  "mx-auto h-px w-6",
                  dark
                    ? "bg-[var(--color-rail-border)]"
                    : "bg-[var(--color-border)]"
                )}
                aria-hidden="true"
              />
            ) : null}
            <div
              className={cn(
                "space-y-0.5",
                collapsed && "flex flex-col items-center"
              )}
            >
              {visibleItems.map((item) => {
                const isActive = activeTab === item.value;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.value}
                    href={`/dashboard/courses/${courseId}?tab=${item.value}`}
                    onClick={onMobileClose}
                    aria-label={item.label}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "flex items-center rounded-[var(--radius-md)] font-medium transition-colors duration-[var(--duration-fast)]",
                      collapsed
                        ? "size-11 justify-center"
                        : "h-10 gap-3 pl-3 pr-2 text-[15px]",
                      isActive
                        ? dark
                          ? "bg-[var(--color-rail-raised)] text-[var(--color-primary)]"
                          : "bg-[var(--color-primary-light)] text-[var(--color-primary)]"
                        : dark
                          ? "text-[var(--color-rail-text-muted)] hover:bg-[var(--color-rail-raised)] hover:text-[var(--color-rail-text)]"
                          : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]"
                    )}
                  >
                    <Icon
                      className={cn(
                        "size-[18px] shrink-0",
                        isActive
                          ? "text-[var(--color-primary)]"
                          : dark
                            ? "text-[var(--color-rail-text-muted)]"
                            : "text-[var(--color-text-muted)]"
                      )}
                      strokeWidth={isActive ? 2.25 : 1.85}
                    />
                    {!collapsed ? <span>{item.label}</span> : null}
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
