"use client";

import { useTranslations } from "next-intl";
import { Menu } from "lucide-react";

import { UserButton } from "@/components/layout/user-button";
import { LanguageToggle } from "@/components/layout/language-toggle";

interface NavbarProps {
  readonly onMenuClick?: () => void;
}

/**
 * The global top bar.
 *
 * It carries product identity, locale, and account, nothing else. It used to
 * render a breadcrumb trail, which duplicated the breadcrumb each page header
 * now owns; the handoff removes duplicated navigation systems ("Remove
 * duplicate links"), and a crumb rendered twice at two different altitudes is
 * exactly that. Location is the page header's job, because only the page knows
 * its own destination title.
 *
 * The hamburger is the automatic responsive affordance below `md`. It is not a
 * user preference and nothing about it is persisted (removal rule 03).
 */
export function Navbar({ onMenuClick }: NavbarProps) {
  const t = useTranslations("nav");

  return (
    <header className="flex h-[68px] shrink-0 items-center justify-between border-b border-[var(--color-border)]/60 bg-[var(--color-surface)] px-4 md:px-8">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          type="button"
          className="flex size-11 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-text-muted)] outline-none transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 motion-reduce:transition-none md:hidden"
          aria-label={t("openNavigation")}
        >
          <Menu className="size-5" aria-hidden="true" />
        </button>

        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
          {t("wordmark")}
        </span>
      </div>

      <div className="flex items-center gap-2">
        <LanguageToggle />
        <UserButton />
      </div>
    </header>
  );
}
