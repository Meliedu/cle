"use client";

import type { ComponentType } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ChevronRight,
  Layers,
  Mic,
  Radio,
  RefreshCw,
  Trophy,
  type LucideProps,
} from "lucide-react";

import { cn } from "@/lib/utils";

interface StudentActivitiesProps {
  readonly courseId: string;
}

interface EntryDef {
  /** i18n key under `student.activities.foldIn` for title + description. */
  readonly key: "flashcards" | "revision" | "pronunciation" | "liveQuiz";
  readonly icon: ComponentType<LucideProps>;
  /** Href into the existing (folded-in) surface — no rebuild (Decision 9). */
  readonly href: (courseId: string) => string;
}

/**
 * The folded-in practice surfaces (Decision 9): each entry LINKS into an
 * already-built flashcard / revision / pronunciation / live-quiz surface rather
 * than re-implementing it. Ordered from lightest to most involved.
 */
const FOLD_IN_ENTRIES: readonly EntryDef[] = [
  {
    key: "flashcards",
    icon: Layers,
    href: (id) => `/dashboard/courses/${id}?tab=flashcards`,
  },
  {
    key: "revision",
    icon: RefreshCw,
    href: (id) => `/dashboard/courses/${id}/revision`,
  },
  {
    key: "pronunciation",
    icon: Mic,
    href: (id) => `/dashboard/courses/${id}?tab=pronunciation`,
  },
  {
    key: "liveQuiz",
    icon: Radio,
    href: (id) => `/dashboard/courses/${id}?tab=live`,
  },
];

/**
 * S031 / S072 — the student Activities home. P5 fills the P4 placeholder: it
 * lists the folded-in practice surfaces (flashcards / revision / pronunciation /
 * live quiz — Decision 9, link-only) and links out to the student's own score &
 * participation record (S059). Mobile-first single column; every row is a large
 * tap target. Never a blank panel.
 */
export function StudentActivities({ courseId }: StudentActivitiesProps) {
  const t = useTranslations("student.activities.list");
  const tf = useTranslations("student.activities.foldIn");

  return (
    <div className="space-y-8">
      <section aria-labelledby="activities-practice-heading" className="space-y-3">
        <div className="space-y-1">
          <h2
            id="activities-practice-heading"
            className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]"
          >
            {t("practiceHeading")}
          </h2>
          <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            {t("practiceDescription")}
          </p>
        </div>

        <ul className="space-y-2.5">
          {FOLD_IN_ENTRIES.map((entry) => (
            <li key={entry.key}>
              <EntryRow
                href={entry.href(courseId)}
                icon={entry.icon}
                title={tf(`${entry.key}.title`)}
                description={tf(`${entry.key}.description`)}
              />
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="activities-record-heading" className="space-y-3">
        <h2
          id="activities-record-heading"
          className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]"
        >
          {t("recordHeading")}
        </h2>
        <EntryRow
          href={`/student/courses/${courseId}/scores`}
          icon={Trophy}
          title={t("scoresTitle")}
          description={t("scoresDescription")}
          highlighted
        />
      </section>
    </div>
  );
}

interface EntryRowProps {
  readonly href: string;
  readonly icon: ComponentType<LucideProps>;
  readonly title: string;
  readonly description: string;
  readonly highlighted?: boolean;
}

function EntryRow({
  href,
  icon: Icon,
  title,
  description,
  highlighted,
}: EntryRowProps) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex items-center gap-3 rounded-[var(--radius-xl)] border px-4 py-3.5 transition-colors duration-[var(--duration-fast)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none",
        highlighted
          ? "border-[var(--color-primary)]/40 bg-[var(--color-primary-light)] hover:bg-[var(--color-primary-light)]/70"
          : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-[var(--color-surface-hover)]"
      )}
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
        <Icon aria-hidden="true" strokeWidth={1.85} className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[14px] font-semibold text-[var(--color-text)]">
          {title}
        </p>
        <p className="text-[13px] leading-snug text-[var(--color-text-secondary)]">
          {description}
        </p>
      </div>
      <ChevronRight
        aria-hidden="true"
        className="size-4 shrink-0 text-[var(--color-text-muted)] transition-transform duration-[var(--duration-fast)] group-hover:translate-x-0.5 motion-reduce:transition-none"
      />
    </Link>
  );
}
