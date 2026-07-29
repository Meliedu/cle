import {
  BarChart3,
  BookOpen,
  Calendar,
  ClipboardList,
  Clock,
  FileText,
  Home,
  LayoutDashboard,
  PencilLine,
  TrendingUp,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { Role } from "@/hooks/use-role";

/**
 * Navigation ownership, per the approved handoff.
 *
 * Two rails, two owners, no overlap:
 *
 *   GLOBAL  role-scoped destinations that exist everywhere in the app.
 *   COURSE  course-scoped destinations that exist ONLY after course entry.
 *
 * Removal rules this file enforces (handoff "Explicitly remove from the
 * implementation"):
 *   01  No global Sessions destination. Sessions is course-local only, and
 *       every session route carries a courseId.
 *   04  No Before Class / In Class / After Class buckets. The course rail is a
 *       flat list of stable destinations.
 *   05  No second horizontal course tab row. The rail is the only course
 *       navigation system.
 */

export interface NavItem {
  /** i18n key under `nav.*`, resolved by the rail at render time. */
  readonly key: string;
  /** Fallback label used when a translation is missing. */
  readonly label: string;
  readonly href: string;
  readonly icon: LucideIcon;
}

/** A course destination, expressed as a path suffix under the course root. */
export interface CourseNavItem {
  readonly key: string;
  readonly label: string;
  /** Suffix under `/{role}/courses/{courseId}`; `null` is the course index. */
  readonly segment: string | null;
  readonly icon: LucideIcon;
}

// ---------------------------------------------------------------------------
// Global rails
// ---------------------------------------------------------------------------

/** Teacher global: Home, Courses, Calendar, Insights. Nothing else. */
export const TEACHER_GLOBAL_NAV: readonly NavItem[] = [
  { key: "home", label: "Home", href: "/teacher/dashboard", icon: Home },
  { key: "courses", label: "Courses", href: "/teacher/courses", icon: BookOpen },
  { key: "calendar", label: "Calendar", href: "/teacher/calendar", icon: Calendar },
  { key: "insights", label: "Insights", href: "/teacher/insights", icon: BarChart3 },
] as const;

/** Student global: Home, Courses, Calendar, My progress. */
export const STUDENT_GLOBAL_NAV: readonly NavItem[] = [
  { key: "home", label: "Home", href: "/student/dashboard", icon: Home },
  { key: "courses", label: "Courses", href: "/student/courses", icon: BookOpen },
  { key: "calendar", label: "Calendar", href: "/student/calendar", icon: Calendar },
  {
    key: "myProgress",
    label: "My progress",
    href: "/student/progress",
    icon: TrendingUp,
  },
] as const;

export function globalNavForRole(role: Role): readonly NavItem[] {
  return role === "instructor" ? TEACHER_GLOBAL_NAV : STUDENT_GLOBAL_NAV;
}

// ---------------------------------------------------------------------------
// Course rails
// ---------------------------------------------------------------------------

/**
 * Teacher course-local: Overview, Sessions, Materials, Activities, Practice,
 * Students, Insights.
 *
 * Sessions sits directly after Overview because it owns the teaching-time
 * spine (Plate 04, rule 2). Reports and Course memory are NOT rail entries:
 * the canonical coverage table files them under Insights (T076–T108), so they
 * are sub-destinations reached from there. Schedule is reached from Sessions.
 * Their routes still exist; they are simply not a ninth and tenth top-level
 * destination.
 */
export const TEACHER_COURSE_NAV: readonly CourseNavItem[] = [
  { key: "overview", label: "Overview", segment: null, icon: LayoutDashboard },
  { key: "sessions", label: "Sessions", segment: "sessions", icon: Clock },
  { key: "materials", label: "Materials", segment: "materials", icon: FileText },
  {
    key: "activities",
    label: "Activities",
    segment: "activities",
    icon: ClipboardList,
  },
  { key: "practice", label: "Practice", segment: "practice", icon: PencilLine },
  { key: "students", label: "Students", segment: "students", icon: Users },
  { key: "insights", label: "Insights", segment: "insights", icon: BarChart3 },
] as const;

/**
 * Student course-local: Overview, Sessions, Materials, Activities, Practice,
 * Progress. No teacher-only management destinations appear (Student 01, note
 * 02).
 */
export const STUDENT_COURSE_NAV: readonly CourseNavItem[] = [
  { key: "overview", label: "Overview", segment: null, icon: LayoutDashboard },
  { key: "sessions", label: "Sessions", segment: "sessions", icon: Clock },
  { key: "materials", label: "Materials", segment: "materials", icon: FileText },
  {
    key: "activities",
    label: "Activities",
    segment: "activities",
    icon: ClipboardList,
  },
  { key: "practice", label: "Practice", segment: "practice", icon: PencilLine },
  { key: "progress", label: "Progress", segment: "progress", icon: TrendingUp },
] as const;

export function courseNavForRole(role: Role): readonly CourseNavItem[] {
  return role === "instructor" ? TEACHER_COURSE_NAV : STUDENT_COURSE_NAV;
}

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

/** `/teacher/courses/:id` or `/student/courses/:id`. */
export function courseRoot(role: Role, courseId: string): string {
  const lane = role === "instructor" ? "teacher" : "student";
  return `/${lane}/courses/${courseId}`;
}

export function courseHref(
  role: Role,
  courseId: string,
  item: CourseNavItem
): string {
  const root = courseRoot(role, courseId);
  return item.segment ? `${root}/${item.segment}` : root;
}

/**
 * The course id currently in scope, or `null` when the user is on a global
 * destination. Course navigation renders only when this is non-null, matching the
 * handoff's "render course navigation only after course entry".
 *
 * Deliberately anchored to `/courses/{id}` so a global route that merely
 * contains the word "courses" (e.g. `/teacher/courses`) yields `null`.
 */
export function activeCourseId(pathname: string): string | null {
  const match = pathname.match(/\/(?:teacher|student|dashboard)\/courses\/([^/?#]+)/);
  if (!match) return null;
  const id = match[1];
  // `/courses/new` is the create form, not a course context.
  if (id === "new") return null;
  // Setup owns the working surface while the course is incomplete: "Suppress
  // steady-state course navigation inside setup; preserve only global context
  // and a safe exit" (Plate 05, rule 2). Returning null here is what removes
  // the course rail, since the rail renders only for a non-null course.
  if (isSetupRoute(pathname)) return null;
  return id;
}

/** Whether a path is inside the transient course-setup flow. */
export function isSetupRoute(pathname: string): boolean {
  return /\/courses\/[^/]+\/setup(?:\/|$|\?)/.test(pathname);
}

/**
 * Which course destination the current path belongs to. Sub-routes resolve to
 * their owning destination so a session detail page keeps "Sessions" lit
 * (one appearance per route hierarchy, boundary rule 03).
 */
export function activeCourseKey(
  pathname: string,
  items: readonly CourseNavItem[]
): string {
  const afterCourse = pathname.match(
    /\/(?:teacher|student|dashboard)\/courses\/[^/]+\/([^/?#]+)/
  );
  if (!afterCourse) return "overview";
  const segment = afterCourse[1];

  const direct = items.find((item) => item.segment === segment);
  if (direct) return direct.key;

  // Sub-destinations that live under a rail entry rather than beside it.
  const OWNED_BY: Record<string, string> = {
    schedule: "sessions",
    checkpoints: "sessions",
    reports: "insights",
    memory: "insights",
    enrollment: "students",
    scores: "students",
    quiz: "activities",
    live: "activities",
    flashcards: "practice",
    revision: "practice",
    pronunciation: "practice",
  };
  return OWNED_BY[segment] ?? "overview";
}
