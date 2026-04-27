import Link from "next/link";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";

/**
 * Landing screen shown right after sign-up. Better Auth has already sent
 * the verification email; clicking the link auto-signs the user in
 * (autoSignInAfterVerification: true) and forwards them to /dashboard.
 */
export default function VerifyEmailPage() {
  return (
    <AuthShell tagline="One last step">
      <AuthCard
        eyebrow="Almost there"
        heading="Check your inbox"
        subtitle="We sent a verification link to your email. Open it from any device and you'll be signed in automatically."
        footer={
          <AuthLinkRow
            question="Wrong address?"
            href="/sign-up"
            cta="Sign up again"
          />
        }
      >
        <ol className="space-y-3 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          <li className="flex gap-3">
            <Step n={1} />
            <span>Open the email we just sent — check spam if it&apos;s missing.</span>
          </li>
          <li className="flex gap-3">
            <Step n={2} />
            <span>Click the verification link to activate your account.</span>
          </li>
          <li className="flex gap-3">
            <Step n={3} />
            <span>You&apos;ll land on your studio dashboard, signed in.</span>
          </li>
        </ol>

        <p className="mt-6 text-[12px] text-[var(--color-text-muted)]">
          Already verified?{" "}
          <Link
            href="/sign-in"
            className="font-semibold text-[var(--color-text)] underline-offset-[3px] hover:underline focus-visible:underline focus-visible:outline-none"
          >
            Sign in
          </Link>
        </p>
      </AuthCard>
    </AuthShell>
  );
}

function Step({ n }: { readonly n: number }) {
  return (
    <span
      aria-hidden="true"
      className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-[var(--color-primary-muted)] bg-[var(--color-primary-light)] text-[10px] font-semibold text-[var(--color-primary-hover)]"
    >
      {n}
    </span>
  );
}
