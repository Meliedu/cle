"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import {
  ArrowUpRight,
  Layers3,
  Mic,
  RefreshCw,
  Radio,
  type LucideIcon,
} from "lucide-react";

interface FoldinLinksProps {
  readonly courseId: string;
}

interface FoldinTarget {
  readonly key: "flashcards" | "pronunciation" | "revision" | "live";
  readonly href: string;
  readonly Icon: LucideIcon;
}

/**
 * F6 fold-in entry points (Decision 9). Links into the EXISTING flashcard /
 * pronunciation / revision / live-quiz surfaces under `dashboard/courses/*`
 * rather than rebuilding them — Activities is the hub, these routes own the
 * behavior.
 */
export function FoldinLinks({ courseId }: FoldinLinksProps) {
  const t = useTranslations("teacher.activities.home.foldins");

  const targets: readonly FoldinTarget[] = [
    {
      key: "flashcards",
      href: `/dashboard/courses/${courseId}?tab=flashcards`,
      Icon: Layers3,
    },
    {
      key: "pronunciation",
      href: `/dashboard/courses/${courseId}?tab=pronunciation`,
      Icon: Mic,
    },
    {
      key: "revision",
      href: `/dashboard/courses/${courseId}/revision`,
      Icon: RefreshCw,
    },
    {
      key: "live",
      href: `/dashboard/courses/${courseId}?tab=live`,
      Icon: Radio,
    },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {targets.map(({ key, href, Icon }) => (
        <Link
          key={key}
          href={href}
          className="group flex items-start gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 transition-colors hover:border-[var(--color-primary)]/50 hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40"
        >
          <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)]">
            <Icon aria-hidden="true" className="size-4 text-[var(--color-primary)]" />
          </span>
          <span className="min-w-0 flex-1 space-y-0.5">
            <span className="flex items-center gap-1 text-[14px] font-semibold text-[var(--color-text)]">
              {t(`${key}.title`)}
              <ArrowUpRight
                aria-hidden="true"
                className="size-3.5 text-[var(--color-text-muted)] transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              />
            </span>
            <span className="block text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
              {t(`${key}.description`)}
            </span>
          </span>
        </Link>
      ))}
    </div>
  );
}
