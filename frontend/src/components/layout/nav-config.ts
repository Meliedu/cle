import { BarChart3, BookOpen, Calendar, GraduationCap, LayoutDashboard } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { Role } from "@/hooks/use-role";

export interface NavItem {
  /** Visible label (English for now; i18n keys arrive with the locale pass). */
  label: string;
  href: string;
  icon: LucideIcon;
}

export const TEACHER_NAV: NavItem[] = [
  { label: "Dashboard", href: "/teacher/dashboard", icon: LayoutDashboard },
  { label: "Courses", href: "/teacher/courses", icon: BookOpen },
  { label: "Calendar", href: "/teacher/calendar", icon: Calendar },
  { label: "Insights", href: "/teacher/insights", icon: BarChart3 },
];

export const STUDENT_NAV: NavItem[] = [
  { label: "Dashboard", href: "/student/dashboard", icon: LayoutDashboard },
  { label: "Courses", href: "/student/courses", icon: GraduationCap },
  { label: "Calendar", href: "/student/calendar", icon: Calendar },
];

export function navForRole(role: Role): NavItem[] {
  return role === "instructor" ? TEACHER_NAV : STUDENT_NAV;
}
