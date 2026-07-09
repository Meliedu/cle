import type { ReactNode } from "react";

import { HoneycombMark } from "@/components/auth/honeycomb-mark";

interface AuthShellProps {
  readonly children: ReactNode;
  readonly tagline?: string;
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
  return (
    <div className="min-h-dvh bg-[var(--color-bg)]">
      <div className="grid min-h-dvh grid-cols-1 lg:grid-cols-12">
        {/* Brand pane — desktop only */}
        <aside
          aria-hidden="true"
          className="relative hidden flex-col justify-between overflow-hidden bg-[var(--color-bg)] px-12 pb-12 pt-14 lg:col-span-7 lg:flex xl:px-20"
        >
          <header className="relative z-10 flex items-center gap-2.5">
            <span
              aria-hidden="true"
              className="inline-flex size-6 items-center justify-center rounded-[6px] bg-[var(--color-primary)] text-[10px] font-bold uppercase tracking-[0.16em] text-[var(--color-text-on-primary)]"
            >
              M
            </span>
            <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-secondary)]">
              Meli · HKUST CLE
            </span>
          </header>

          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <HoneycombMark className="size-[min(620px,72%)]" />
          </div>

          <footer className="relative z-10 max-w-[38ch] space-y-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-text-muted)]">
              {tagline ?? "The checkpoint-centred course loop"}
            </p>
            <p className="font-display text-[1.6rem] font-semibold leading-[1.15] text-[var(--color-text)]">
              A reviewed loop from course materials to a clear next action.
            </p>
            <p className="text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
              Teachers review and publish checkpoints; students act from a
              checklist, a calendar, or a QR scan in class.
            </p>
            <p className="pt-2 text-[11px] tracking-[0.04em] text-[var(--color-text-muted)]">
              Available to instructors at <span className="font-medium text-[var(--color-text-secondary)]">@ust.hk</span>{" "}
              · students at <span className="font-medium text-[var(--color-text-secondary)]">@connect.ust.hk</span>
            </p>
          </footer>
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
              Meli
            </span>
          </div>

          <div className="w-full max-w-[26rem]">{children}</div>
        </main>
      </div>
    </div>
  );
}
