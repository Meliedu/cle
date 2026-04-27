import type { ReactNode } from "react";

interface AuthCardProps {
  readonly eyebrow: string;
  readonly heading: string;
  readonly subtitle: ReactNode;
  readonly children: ReactNode;
  readonly footer?: ReactNode;
}

/**
 * Shared editorial structure for every auth screen:
 *
 *   [eyebrow]    — uppercase 11px tracking-[0.22em] muted
 *   [heading]    — semibold tracking-tight clamp display
 *   [subtitle]   — 14px secondary, max ~44ch
 *   [children]   — slot for the form / actions / status
 *   [footer]     — micro-line link row (sign in ↔ sign up etc.)
 *
 * Mounts with a single soft enter (translate-y + opacity, ≤300ms, gated on
 * prefers-reduced-motion via globals.css). No layout-property animation.
 */
export function AuthCard({
  eyebrow,
  heading,
  subtitle,
  children,
  footer,
}: AuthCardProps) {
  return (
    <article className="auth-card relative rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-7 shadow-[var(--shadow-shell)] sm:px-8 sm:py-8">
      <header className="space-y-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-primary-hover)]">
          {eyebrow}
        </p>
        <h1 className="text-[clamp(1.625rem,1.25rem+1vw,2rem)] font-semibold leading-[1.1] tracking-tight text-[var(--color-text)]">
          {heading}
        </h1>
        <p className="max-w-[44ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          {subtitle}
        </p>
      </header>

      <div className="mt-7">{children}</div>

      {footer ? (
        <footer className="mt-7 border-t border-[var(--color-border)]/70 pt-5 text-center text-[12px] text-[var(--color-text-muted)]">
          {footer}
        </footer>
      ) : null}
    </article>
  );
}
