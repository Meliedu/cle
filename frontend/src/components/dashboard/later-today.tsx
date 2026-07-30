"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { TeachingEntry } from "@/lib/teaching-day";

interface LaterTodayProps {
  readonly entries: readonly TeachingEntry[];
}

/**
 * The compact subordinate region beneath the hero (Plate 01, rule 3):
 *
 *   Later-today work and roster are compact subordinate regions.
 *   Enforce one primary action per dashboard state; all other rows use text
 *   actions or quiet status.
 *
 * Every row here is a link with a quiet status chip. There is no filled button
 * anywhere in this component; that budget belongs to the hero.
 */
export function LaterToday({ entries }: LaterTodayProps) {
  const t = useTranslations("teacher.home");
  const locale = useLocale();

  return (
    <section aria-labelledby="later-today-title">
      <h2
        id="later-today-title"
        className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
      >
        {t("laterToday.title")}
      </h2>

      {entries.length === 0 ? (
        <p className="mt-3 border-t border-[var(--color-border)] pt-4 text-[14px] text-[var(--color-text-muted)]">
          {t("laterToday.empty")}
        </p>
      ) : (
        <ul className="mt-3 border-t border-[var(--color-border)]">
          {entries.map((entry) => (
            <li key={entry.id} className="border-b border-[var(--color-border)]">
              <Link
                href={`/teacher/courses/${entry.courseId}`}
                className="flex min-h-[60px] flex-wrap items-center gap-x-5 gap-y-1 rounded-[var(--radius-md)] px-2 py-3 outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none"
              >
                <time
                  dateTime={entry.at}
                  className="w-14 shrink-0 text-[14px] font-medium tabular-nums text-[var(--color-text-secondary)]"
                >
                  {new Date(entry.at).toLocaleTimeString(locale, {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>

                <div className="min-w-0 flex-1">
                  <p className="truncate text-[15px] font-medium text-[var(--color-text)]">
                    {entry.title}
                  </p>
                  <p className="mt-0.5 truncate text-[13px] text-[var(--color-text-muted)]">
                    {[
                      entry.courseCode,
                      entry.location,
                      entry.provenance,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>

                <KindChip kind={entry.kind} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Quiet status. The label states the entry type in words; the tint is
 * supplementary, so the row still reads correctly in greyscale.
 */
function KindChip({ kind }: { readonly kind: TeachingEntry["kind"] }) {
  const t = useTranslations("teacher.home");

  const tone: Record<TeachingEntry["kind"], string> = {
    class:
      "border-[var(--color-gold)]/45 bg-[var(--color-cream)] text-[var(--color-primary-text)]",
    generated_release:
      "border-[var(--color-accent)]/35 bg-[var(--color-accent-light)] text-[var(--color-accent-hover)]",
    deadline:
      "border-[var(--color-coral)]/40 bg-[var(--color-coral-soft)]/50 text-[var(--color-text-secondary)]",
    assignment:
      "border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)]",
  };

  return (
    <span
      className={cn(
        "inline-flex h-6 shrink-0 items-center rounded-[var(--radius-pill)] border px-2.5 text-[12px] font-medium",
        tone[kind]
      )}
    >
      {t(`kind.${kind}`)}
    </span>
  );
}
