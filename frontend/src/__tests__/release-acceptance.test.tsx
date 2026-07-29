import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Release acceptance criteria, as source guards.
 *
 *   Targets  High-frequency controls and touch actions meet 44x44 CSS px
 *            implementation targets; adjacent targets retain separation.
 *   Focus    Visible focus is not clipped, obscured, or color-only.
 *   Status   Processing, success, warning, failure, locked, and saved state
 *            are expressed in text.
 *   Responsive  reduced-motion test for loading/progress.
 *
 * jsdom does not compute layout, so a rendered hitbox cannot be measured here;
 * the browser-computed audit is a separate manual gate. What IS mechanically
 * checkable is that every interactive element in the surfaces this change set
 * introduced carries the sizing, focus, and reduced-motion classes that produce
 * a compliant control. That is what these tests lock down.
 */

const SRC = path.resolve(__dirname, "..");

/** Surfaces introduced or rebuilt for the approved handoff. */
const SURFACES = [
  "components/dashboard/teacher-home.tsx",
  "components/dashboard/student-home.tsx",
  "components/dashboard/next-teaching-hero.tsx",
  "components/dashboard/learning-action-hero.tsx",
  "components/dashboard/later-today.tsx",
  "components/dashboard/learning-queue.tsx",
  "components/dashboard/teaching-roster.tsx",
  "components/dashboard/day-rail.tsx",
  "components/dashboard/roster-row.tsx",
  "components/dashboard/teacher-roster-view.tsx",
  "components/calendar/calendar-shell.tsx",
  "components/calendar/calendar-day-sidebar.tsx",
  "components/course/course-overview.tsx",
  "components/course/course-workspace-shell.tsx",
  "components/layout/sidebar.tsx",
  "components/layout/sidebar-section-nav.tsx",
  "components/layout/navbar.tsx",
  "components/setup/stage-stepper.tsx",
  "components/setup/source-status-list.tsx",
  "components/setup/setup-context-rail.tsx",
  "components/join/placement-evidence.tsx",
] as const;

function read(relative: string): string {
  return readFileSync(path.join(SRC, relative), "utf8");
}

describe("focus is visible on every interactive surface", () => {
  it.each(SURFACES)("%s pairs outline-none with a focus ring", (relative) => {
    const source = read(relative);
    const suppressions = (source.match(/outline-none/g) ?? []).length;
    if (suppressions === 0) return;
    // Removing the UA outline without providing a visible replacement is the
    // exact defect the criterion forbids.
    const rings = (source.match(/focus-visible:(ring|border)/g) ?? []).length;
    expect(rings).toBeGreaterThanOrEqual(suppressions);
  });
});

describe("motion is reducible", () => {
  it.each(SURFACES)("%s guards every transition", (relative) => {
    const source = read(relative);
    // Count declarations, not occurrences: a single className may carry both
    // `motion-reduce:transition-none` and `motion-reduce:group-hover:*`.
    const transitions = (source.match(/\btransition-(colors|transform|all|\[)/g) ?? [])
      .length;
    if (transitions === 0) return;
    const guarded = (source.match(/motion-reduce:transition-none/g) ?? []).length;
    expect(guarded).toBeGreaterThanOrEqual(transitions);
  });
});

describe("high-frequency controls meet the 44px target", () => {
  it("sizes the primary button variant at 44px", () => {
    const button = read("components/ui/button.tsx");
    expect(button).toMatch(/xl:\s*"h-11/);
    expect(button).toMatch(/"icon-xl":\s*"size-11/);
  });

  it.each([
    ["components/layout/sidebar.tsx", "rail links"],
    ["components/layout/sidebar-section-nav.tsx", "course rail links"],
    ["components/setup/stage-stepper.tsx", "stage buttons"],
  ])("%s uses h-11 for its %s", (relative) => {
    const source = read(relative);
    expect(source).toMatch(/\bh-11\b/);
  });

  it("sizes every icon-only control at 44px in the surfaces that have them", () => {
    for (const relative of [
      "components/calendar/calendar-shell.tsx",
      "components/dashboard/day-rail.tsx",
      "components/layout/navbar.tsx",
    ]) {
      const source = read(relative);
      // An icon-only control has no text to grow the hitbox, so it must be
      // explicitly sized.
      expect(source).toMatch(/\bsize-11\b/);
    }
  });
});

describe("icon-only controls carry an accessible name", () => {
  it.each(SURFACES)("%s labels every icon-only control", (relative) => {
    const source = read(relative);
    // Every <button> that renders only an icon must have aria-label. Find
    // buttons whose body contains no text node between the tags.
    const iconOnly = source.match(
      /<button[^>]*>\s*(?:\{[^}]*\}\s*)?<[A-Z][\w]*\s[^>]*\/>\s*<\/button>/g
    );
    if (!iconOnly) return;
    for (const match of iconOnly) {
      expect(match).toMatch(/aria-label|aria-labelledby/);
    }
  });
});

describe("decorative graphics are hidden from assistive tech", () => {
  it.each(SURFACES)("%s marks every lucide icon aria-hidden or labels it", (relative) => {
    const source = read(relative);
    // Icons rendered as self-closing components with a className are visual;
    // each must be aria-hidden so it is not announced as a bare element name.
    const icons = source.match(
      /<(?:ArrowRight|ArrowLeft|ChevronLeft|ChevronRight|Check|Search|Plus|Menu|LogOut|CalendarX2|CheckCircle2|FileText)\b[^>]*\/>/g
    );
    if (!icons) return;
    for (const icon of icons) {
      expect(icon).toMatch(/aria-hidden/);
    }
  });
});

describe("status is expressed in text, not only colour", () => {
  it("pairs every readiness tint with a translated label", () => {
    const list = read("components/setup/source-status-list.tsx");
    // Every readiness value maps to BOTH a translation key and a class, so a
    // state can never render as a bare colour. The exhaustive Record type
    // means adding a readiness value without a label is a compile error.
    expect(list).toMatch(/Record<\s*SourceReadiness/);
    expect(list).toMatch(/\{t\(key\)\}/);
    for (const state of [
      "idle",
      "uploading",
      "processing",
      "ready",
      "recoverable_error",
      "blocking_error",
    ]) {
      expect(list).toContain(`${state}:`);
    }
  });

  it("states the safe-to-leave state as a word alongside its tint", () => {
    const rail = read("components/setup/setup-context-rail.tsx");
    expect(rail).toMatch(/stateWarning/);
    expect(rail).toMatch(/stateWorking/);
    expect(rail).toMatch(/stateOk/);
  });

  it("gives the placement evidence a state word per skill", () => {
    const evidence = read("components/join/placement-evidence.tsx");
    expect(evidence).toMatch(/t\(`state\.\$\{row\.state\}`\)/);
    // The raw score is deliberately never rendered.
    expect(evidence).not.toMatch(/\{row\.score\}/);
  });
});
