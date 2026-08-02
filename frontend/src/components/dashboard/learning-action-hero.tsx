"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { CheckCircle2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { courseTitle } from "@/lib/format";
import { actionVerbKey, type LearningAction } from "@/lib/learning-path";

interface LearningActionHeroProps {
  readonly action: LearningAction | null;
}

/**
 * The learner's single next action (Student 01, note 01).
 *
 *   Home resolves one recoverable next action with saved progress, source, due
 *   time, and a direct resume action.
 *
 * All four are present and all four are text. "Saved" is stated in words rather
 * than implied by a progress ring, because the release contract requires saved
 * state to be understandable without color or animation.
 */
export function LearningActionHero({ action }: LearningActionHeroProps) {
  const t = useTranslations("student.home");
  const locale = useLocale();

  if (!action) return <AllClear />;

  const { item } = action;
  const verb = actionVerbKey(action);
  const now = new Date();
  const due = item.due_at ? new Date(item.due_at) : null;
  const isToday = due ? isSameDay(due, now) : false;
  // The hero only holds actionable work, so a past due date means "still
  // open, but late" and must be said in words, not left as a stale date
  // dressed up as a plan.
  const overdue = Boolean(due && due < now);

  const lead = overdue
    ? t("leadOverdue", {
        date: formatDate(due as Date, locale),
        time: formatTime(due as Date, locale),
      })
    : action.work === "in_progress"
      ? due
        ? isToday
          ? t("leadDueToday", { time: formatTime(due, locale) })
          : t("leadDueOn", {
              date: formatDate(due, locale),
              time: formatTime(due, locale),
            })
        : t("leadNoDue")
      : t("leadStart");

  // A source_kind the messages file does not know would render the raw key
  // path ("student.home.kind.whatever") to the learner. The backend owns this
  // enum and can add to it, so fall back rather than trust the union.
  const KNOWN_KINDS = [
    "checkpoint",
    "practice",
    "quiz",
    "activity",
    "material",
    "follow_up",
    "report",
  ];
  const meta = [
    KNOWN_KINDS.includes(item.source_kind)
      ? t(`kind.${item.source_kind}`)
      : t("kind.other"),
    due
      ? t(overdue ? "wasDueAt" : "dueAt", {
          date: formatDate(due, locale),
          time: formatTime(due, locale),
        })
      : t("noDue"),
  ];

  return (
    <section
      aria-labelledby="learning-next-title"
      className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--color-gold)]/45 bg-[var(--color-cream)] pl-[5px]"
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[5px] bg-[var(--color-primary)]"
      />

      <div className="flex flex-col gap-6 px-6 py-6 md:px-8 md:py-7 lg:flex-row lg:items-center lg:justify-between lg:gap-10">
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-semibold tracking-tight text-[var(--color-primary-text)]">
            {lead}
          </p>

          {/* Saved state, said in words. */}
          <p className="mt-3 inline-flex h-7 items-center rounded-[var(--radius-md)] bg-[var(--color-success-light)] px-2.5 text-[12px] font-medium text-[var(--color-success)]">
            {t(`chip.${verb}`)}
          </p>

          <h2
            id="learning-next-title"
            className="mt-3 text-[26px] font-semibold leading-tight tracking-[-0.02em] text-[var(--color-text)] md:text-[30px]"
          >
            {item.title}
          </h2>

          <p className="mt-1.5 text-[15px] text-[var(--color-text-secondary)]">
            {action.courseCode} · {courseTitle(action.courseCode, action.courseName)}
          </p>

          <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[var(--color-gold)]/35 pt-4 text-[14px] text-[var(--color-text-secondary)]">
            {meta.map((value) => (
              <span key={value}>{value}</span>
            ))}
          </p>
        </div>

        <Button
          size="xl"
          className="shrink-0"
          render={<Link href={destinationFor(action)} />}
        >
          {t(`verb.${verb}`, { title: item.title })}
        </Button>
      </div>
    </section>
  );
}

/**
 * An empty checklist is a good outcome, so it reads as one. It is not an error
 * state and does not offer an action the learner cannot take.
 */
function AllClear() {
  const t = useTranslations("student.home");
  return (
    <section className="rounded-[var(--radius-2xl)] border border-[var(--color-success)]/35 bg-[var(--color-success-light)] px-6 py-10 text-center">
      <span className="mx-auto flex size-11 items-center justify-center rounded-full bg-[var(--color-surface)]">
        <CheckCircle2
          aria-hidden="true"
          strokeWidth={1.7}
          className="size-5 text-[var(--color-success)]"
        />
      </span>
      <h2 className="mt-4 text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
        {t("allClearTitle")}
      </h2>
      <p className="mx-auto mt-1.5 max-w-[52ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
        {t("allClearReason")}
      </p>
    </section>
  );
}

/**
 * Where the action opens.
 *
 * Every destination is course-scoped, because a session or practice route
 * without its course is exactly the detached-inventory pattern the handoff
 * removes.
 */
export function destinationFor(action: LearningAction): string {
  const base = `/student/courses/${action.courseId}`;
  switch (action.item.source_kind) {
    case "checkpoint":
      return `${base}/checkpoints`;
    case "practice":
    case "quiz":
      return action.item.source_id
        ? `${base}/practice/${action.item.source_id}`
        : `${base}/activities`;
    case "activity":
      return action.item.source_id
        ? `${base}/activities/${action.item.source_id}`
        : `${base}/activities`;
    case "material":
      return `${base}/materials`;
    case "follow_up":
      return action.item.source_id
        ? `${base}/follow-ups/${action.item.source_id}`
        : base;
    case "report":
      return `${base}/reports`;
  }
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function formatTime(date: Date, locale: string): string {
  return date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

function formatDate(date: Date, locale: string): string {
  return date.toLocaleDateString(locale, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
