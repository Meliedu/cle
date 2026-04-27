import Link from "next/link";

interface AuthLinkRowProps {
  readonly question: string;
  readonly href: string;
  readonly cta: string;
}

/**
 * Footer micro-line in the dashboard's editorial style: question + dot +
 * accent link. Lives inside <AuthCard>'s footer slot.
 */
export function AuthLinkRow({ question, href, cta }: AuthLinkRowProps) {
  return (
    <span className="text-[12px] tracking-[0.01em] text-[var(--color-text-muted)]">
      {question}
      <span aria-hidden="true" className="mx-1.5">
        ·
      </span>
      <Link
        href={href}
        className="font-semibold text-[var(--color-text)] underline-offset-[3px] transition-colors duration-[var(--duration-fast)] hover:text-[var(--color-primary-hover)] hover:underline focus-visible:rounded-sm focus-visible:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]"
      >
        {cta}
      </Link>
    </span>
  );
}
