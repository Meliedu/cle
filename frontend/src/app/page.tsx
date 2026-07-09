import Link from "next/link";
import {
  ArrowRight,
  ClipboardCheck,
  QrCode,
  ListChecks,
  MessageSquareText,
  ShieldCheck,
  Archive,
  BookOpenCheck,
  GraduationCap,
  CircleCheckBig,
} from "lucide-react";

import { cn } from "@/lib/utils";

// The six-stage course operating loop, straight from the CLE service report.
// Concrete operating language only — no hype, no "AI magic" framing.
const LOOP = [
  {
    icon: BookOpenCheck,
    title: "Course context",
    body: "Teachers upload syllabus, materials and schedule; Meli drafts a course map they review and approve.",
  },
  {
    icon: ClipboardCheck,
    title: "Checkpoint planning",
    body: "Session checkpoints are generated from real sources, then edited, timed and published by the teacher.",
  },
  {
    icon: QrCode,
    title: "Student action",
    body: "Students scan in, answer review-point cards and report confidence — action-first, from checklist or QR.",
  },
  {
    icon: MessageSquareText,
    title: "Evidence review",
    body: "Source-linked signals surface for the teacher to review before any feedback reaches a student.",
  },
  {
    icon: ListChecks,
    title: "Follow-up",
    body: "Weak points become revisit work in the student's checklist — support, never punishment.",
  },
  {
    icon: Archive,
    title: "Course memory",
    body: "What worked and what to change is kept, reviewed and carried forward into next term's setup.",
  },
] as const;

const PRINCIPLES = [
  {
    icon: ShieldCheck,
    title: "Nothing reaches students unreviewed",
    body: "Every checkpoint, report and follow-up crosses an explicit teacher-controlled state before it publishes.",
  },
  {
    icon: CircleCheckBig,
    title: "Source-grounded, or it waits",
    body: "If Meli can't cite a source, the item enters “needs source check” rather than appearing polished.",
  },
  {
    icon: GraduationCap,
    title: "Course-scoped, not surveillance",
    body: "Meli describes participation and learning patterns for the course — no time-tracking, no identity claims.",
  },
] as const;

export default function HomePage() {
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-honey-mesh bg-grain">
      {/* Header */}
      <header className="relative z-10 mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5 md:px-10">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-[var(--radius-lg)] bg-[var(--color-rail)] text-[var(--color-primary)]">
            <BookOpenCheck className="size-5" strokeWidth={2} />
          </span>
          <span className="font-display text-[1.35rem] font-semibold leading-none text-[var(--color-text)]">
            Meli
          </span>
        </div>
        <nav className="flex items-center gap-2 sm:gap-3">
          <Link
            href="/sign-in"
            className="rounded-[var(--radius-lg)] px-4 py-2 text-sm font-medium text-[var(--color-text-secondary)] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-[var(--color-text-on-primary)] shadow-[var(--shadow-sm)] transition-all duration-[var(--duration-fast)] hover:bg-[var(--color-primary-hover)] hover:shadow-[var(--shadow-md)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
          >
            Get started
          </Link>
        </nav>
      </header>

      <main className="relative z-10 flex flex-1 flex-col">
        {/* Hero */}
        <section className="mx-auto w-full max-w-6xl px-6 pt-14 pb-16 md:px-10 md:pt-24 md:pb-24">
          <div className="stagger max-w-3xl">
            <span className="inline-flex items-center gap-2 rounded-[var(--radius-pill)] border border-[var(--color-border)] bg-[var(--color-surface)]/80 px-3.5 py-1.5 text-xs font-medium text-[var(--color-text-secondary)] backdrop-blur">
              <span className="size-1.5 rounded-full bg-[var(--color-primary)]" />
              HKUST Centre for Language Education · Chinese pilot
            </span>

            <h1 className="mt-6 font-display text-[clamp(2.5rem,1.6rem+4vw,4.25rem)] font-semibold leading-[1.02] tracking-[-0.02em] text-[var(--color-text)]">
              Turn course materials into a{" "}
              <span className="text-[var(--color-primary-hover)]">
                reviewed learning habit
              </span>
              .
            </h1>

            <p className="mt-6 max-w-xl text-[var(--text-lg)] leading-relaxed text-[var(--color-text-secondary)]">
              Meli is a checkpoint-centred course loop for HKUST CLE Chinese
              courses. Teachers review and publish; students get a clear next
              action every session — from a checklist, a calendar, or a QR scan
              in class.
            </p>

            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href="/sign-up"
                className="group inline-flex items-center justify-center gap-2 rounded-[var(--radius-lg)] bg-[var(--color-primary)] px-6 py-3.5 text-sm font-semibold text-[var(--color-text-on-primary)] shadow-[var(--shadow-md)] transition-all duration-[var(--duration-normal)] ease-[var(--ease-out)] hover:bg-[var(--color-primary-hover)] hover:shadow-[var(--shadow-lg)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
              >
                Get started
                <ArrowRight className="size-4 transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5" />
              </Link>
              <Link
                href="/sign-in"
                className="inline-flex items-center justify-center gap-2 rounded-[var(--radius-lg)] border border-[var(--color-border-hover)] bg-[var(--color-surface)]/70 px-6 py-3.5 text-sm font-semibold text-[var(--color-text)] backdrop-blur transition-all duration-[var(--duration-normal)] ease-[var(--ease-out)] hover:bg-[var(--color-surface)] hover:shadow-[var(--shadow-sm)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
              >
                Sign in
              </Link>
              <span className="text-[13px] text-[var(--color-text-muted)] sm:ml-2">
                Staff <span className="text-[var(--color-border-hover)]">·</span>{" "}
                connect.ust.hk students
              </span>
            </div>
          </div>
        </section>

        {/* The loop */}
        <section className="border-t border-[var(--color-border)]/70 bg-[var(--color-surface)]/60 backdrop-blur">
          <div className="mx-auto w-full max-w-6xl px-6 py-16 md:px-10 md:py-20">
            <div className="max-w-2xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-primary-hover)]">
                One loop, two lanes
              </p>
              <h2 className="mt-3 font-display text-[clamp(1.75rem,1.3rem+1.6vw,2.5rem)] font-semibold leading-[1.1] text-[var(--color-text)]">
                The course operating loop
              </h2>
              <p className="mt-3 text-[15px] leading-relaxed text-[var(--color-text-secondary)]">
                Reviewed context becomes checkpoint-centred student action; reviewed
                evidence becomes teacher action, student insight, and course memory.
              </p>
            </div>

            <ol className="stagger mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {LOOP.map((step, i) => (
                <li
                  key={step.title}
                  className="hover-lift group rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5 hover:border-[var(--color-border-hover)] hover:shadow-[var(--shadow-md)]"
                >
                  <div className="flex items-center justify-between">
                    <span className="grid size-10 place-items-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary-hover)] transition-colors duration-[var(--duration-fast)] group-hover:bg-[var(--color-primary)] group-hover:text-[var(--color-text-on-primary)]">
                      <step.icon className="size-5" strokeWidth={2} />
                    </span>
                    <span className="font-display text-[1.4rem] font-semibold text-[var(--color-border-hover)]">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                  </div>
                  <h3 className="mt-4 text-[15px] font-semibold text-[var(--color-text)]">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-[var(--color-text-muted)]">
                    {step.body}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Two lanes */}
        <section className="mx-auto w-full max-w-6xl px-6 py-16 md:px-10 md:py-20">
          <div className="grid gap-4 md:grid-cols-2">
            <LaneCard
              tag="For students"
              title="A clear next action, never a dashboard"
              points={[
                "Checklist and calendar first — what's due, what's optional, what affects your standing.",
                "Scan into class, answer review-point cards, report how confident you feel from −2 to +2.",
                "Follow-up work appears as support when a concept needs another look.",
              ]}
            />
            <LaneCard
              tag="For teachers"
              title="A review and publish cockpit"
              points={[
                "Generated checkpoints arrive as drafts — edit, remove with a reason, time, and publish.",
                "Review source-linked evidence and decide what students receive.",
                "Keep what worked as course memory and carry it forward next term.",
              ]}
              accent
            />
          </div>
        </section>

        {/* Principles */}
        <section className="border-t border-[var(--color-border)]/70 bg-[var(--color-surface)]/60 backdrop-blur">
          <div className="mx-auto w-full max-w-6xl px-6 py-16 md:px-10 md:py-20">
            <div className="stagger grid gap-6 sm:grid-cols-3">
              {PRINCIPLES.map((p) => (
                <div key={p.title} className="flex flex-col gap-3">
                  <span className="grid size-10 place-items-center rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[var(--color-primary-hover)] shadow-[var(--shadow-sm)] ring-1 ring-[var(--color-border)]">
                    <p.icon className="size-5" strokeWidth={2} />
                  </span>
                  <h3 className="text-[15px] font-semibold leading-snug text-[var(--color-text)]">
                    {p.title}
                  </h3>
                  <p className="text-[13.5px] leading-relaxed text-[var(--color-text-muted)]">
                    {p.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-[var(--color-border)]/70 bg-[var(--color-surface)]/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-6 py-6 text-[13px] text-[var(--color-text-muted)] sm:flex-row md:px-10">
          <span className="font-display text-[15px] text-[var(--color-text-secondary)]">
            Meli
          </span>
          <span>HKUST Centre for Language Education · LANG1511–1515 pilot</span>
        </div>
      </footer>
    </div>
  );
}

function LaneCard({
  tag,
  title,
  points,
  accent = false,
}: {
  tag: string;
  title: string;
  points: readonly string[];
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "hover-lift rounded-[var(--radius-2xl)] border p-7 md:p-8",
        accent
          ? "border-[var(--color-rail-border)] bg-[var(--color-rail)] text-[var(--color-rail-text)]"
          : "border-[var(--color-border)] bg-[var(--color-surface)]"
      )}
    >
      <p
        className={cn(
          "text-[11px] font-semibold uppercase tracking-[0.2em]",
          accent ? "text-[var(--color-primary)]" : "text-[var(--color-primary-hover)]"
        )}
      >
        {tag}
      </p>
      <h3
        className={cn(
          "mt-3 font-display text-[1.5rem] font-semibold leading-tight",
          accent ? "text-[var(--color-surface)]" : "text-[var(--color-text)]"
        )}
      >
        {title}
      </h3>
      <ul className="mt-5 space-y-3">
        {points.map((pt) => (
          <li key={pt} className="flex gap-3">
            <CircleCheckBig
              className={cn(
                "mt-0.5 size-4 shrink-0",
                accent ? "text-[var(--color-primary)]" : "text-[var(--color-primary-hover)]"
              )}
              strokeWidth={2.2}
            />
            <span
              className={cn(
                "text-[14px] leading-relaxed",
                accent
                  ? "text-[var(--color-rail-text)]"
                  : "text-[var(--color-text-secondary)]"
              )}
            >
              {pt}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
