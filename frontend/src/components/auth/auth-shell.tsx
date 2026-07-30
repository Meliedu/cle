import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { BookOpen, ListChecks, QrCode } from "lucide-react";

import { HoneycombMark } from "@/components/auth/honeycomb-mark";

export type AuthTagline =
  | "signIn"
  | "signUp"
  | "forgotPassword"
  | "resetPassword"
  | "verifyEmail";

interface AuthShellProps {
  readonly children: ReactNode;
  /** Key into `auth.tagline.*`, so the eyebrow is localised like everything else. */
  readonly tagline?: AuthTagline;
}

/**
 * Editorial two-pane layout for the auth surface.
 *
 * - Desktop ≥1024px: 7/5 split. Left pane shows the honeycomb cluster on a
 *   warm bone field with editorial typography. Right pane is the auth card.
 * - Mobile <1024px: brand pane collapses; the card scrolls on its own warm
 *   field with safe-area padding.
 *
 * The shell deliberately avoids the "centered modal on grey backdrop"
 * pattern in favor of an editorial composition coherent with the dashboard.
 */
export function AuthShell({ children, tagline }: AuthShellProps) {
  const t = useTranslations("auth");

  return (
    <div className="min-h-dvh bg-[var(--color-bg)]">
      <div className="grid min-h-dvh grid-cols-1 lg:grid-cols-12">
        {/*
          Brand pane, desktop only.

          NOT aria-hidden. It carries the one thing a person stuck at this
          screen actually needs: which HKUST account signs in. Hiding the whole
          pane from assistive tech hid that guidance too.

          The layout is a centred stack rather than justify-between. With only
          a header and a footer the pane had a screen-height void in the middle
          and pushed the useful copy below the fold on shorter windows.
        */}
        <aside className="relative hidden flex-col overflow-hidden bg-[var(--color-bg)] px-12 pb-12 pt-14 lg:col-span-7 lg:flex xl:px-20">
          <header className="relative z-10 flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="inline-flex size-6 items-center justify-center rounded-[6px] bg-[var(--color-primary)] text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--color-text-on-primary)]"
            >
              M
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
              {t("brand")}
            </span>
          </header>

          {/* Background texture only. Anchored bottom-right and well behind
              the copy: as a mid-pane element it read as a stray artifact
              colliding with the headline rather than as decoration. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -bottom-32 -right-32 z-0 opacity-[0.18]"
          >
            <HoneycombMark className="size-[min(560px,52vw)]" />
          </div>

          <div className="relative z-10 flex flex-1 flex-col justify-center py-10">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-muted)]">
              {tagline ? t(`tagline.${tagline}`) : t("eyebrow")}
            </p>
            <h2 className="mt-3 max-w-[20ch] font-display text-[2rem] font-semibold leading-[1.12] text-[var(--color-text)]">
              {t("heading")}
            </h2>
            <p className="mt-3 max-w-[42ch] text-[15px] leading-relaxed text-[var(--color-text-secondary)]">
              {t("body")}
            </p>

            <p className="mt-4 max-w-[42ch] text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
              {t.rich("domains", {
                staff: (chunks) => (
                  <span className="font-medium text-[var(--color-text)]">
                    {chunks}
                  </span>
                ),
                student: (chunks) => (
                  <span className="font-medium text-[var(--color-text)]">
                    {chunks}
                  </span>
                ),
              })}
            </p>

            <div className="mt-9 max-w-[46ch] border-t border-[var(--color-border)] pt-7">
              <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                {t("insideTitle")}
              </h3>
              <ul className="mt-4 space-y-4">
                {[
                  { icon: BookOpen, key: "courses" },
                  { icon: ListChecks, key: "action" },
                  { icon: QrCode, key: "checkIn" },
                ].map(({ icon: Icon, key }) => (
                  <li key={key} className="flex gap-3">
                    <span
                      aria-hidden="true"
                      className="mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[var(--color-primary-hover)] ring-1 ring-[var(--color-border)]"
                    >
                      <Icon className="size-4" strokeWidth={1.9} />
                    </span>
                    <span>
                      <span className="block text-[14px] font-medium text-[var(--color-text)]">
                        {t(`inside.${key}Title`)}
                      </span>
                      <span className="block text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
                        {t(`inside.${key}Body`)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </aside>

        {/* Card pane */}
        <main className="relative col-span-1 flex items-center justify-center px-4 py-10 sm:px-6 lg:col-span-5 lg:bg-[var(--color-surface-raised)] lg:py-16">
          {/* Mobile-only top brand row */}
          <div className="absolute left-1/2 top-6 flex -translate-x-1/2 items-center gap-2 lg:hidden">
            <span
              aria-hidden="true"
              className="inline-flex size-5 items-center justify-center rounded-[5px] bg-[var(--color-primary)] text-[9px] font-bold uppercase tracking-[0.16em] text-[var(--color-text-on-primary)]"
            >
              M
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
              {t("brand")}
            </span>
          </div>

          <div className="w-full max-w-[26rem]">{children}</div>
        </main>
      </div>
    </div>
  );
}
