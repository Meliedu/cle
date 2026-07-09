"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";
import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { authClient } from "@/lib/auth-client";
import { isEmailPasswordHost } from "@/lib/auth-flags";

interface FieldErrors {
  email?: string;
  form?: string;
}

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const emailRef = useRef<HTMLInputElement | null>(null);

  // Host-gated like sign-in/sign-up: password reset only exists on the
  // email/password path, so SSO-only hosts (production) bounce to /sign-in.
  // `null` = not yet resolved (hostname is only available after mount).
  const [allowed, setAllowed] = useState<boolean | null>(null);
  useEffect(() => {
    const ok = isEmailPasswordHost(window.location.hostname);
    setAllowed(ok);
    if (!ok) router.replace("/sign-in");
  }, [router]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      setErrors({ email: "Email is required." });
      emailRef.current?.focus();
      return;
    }
    if (!/.+@.+\..+/.test(trimmed)) {
      setErrors({ email: "Enter a valid email address." });
      emailRef.current?.focus();
      return;
    }
    setErrors({});
    setBusy(true);
    const { error } = await authClient.requestPasswordReset({
      email: trimmed,
      redirectTo: "/reset-password",
    });
    setBusy(false);
    if (error) {
      setErrors({ form: error.message ?? "Could not send reset email." });
      return;
    }
    setSent(true);
  };

  // Nothing renders until the host check resolves (and never on SSO-only
  // hosts, which are already being redirected).
  if (!allowed) return null;

  return (
    <AuthShell tagline="Recover your account">
      <AuthCard
        eyebrow="Reset password"
        heading={sent ? "Check your inbox" : "Forgot your password?"}
        subtitle={
          sent
            ? "If an account exists for that email, a reset link is on its way. The link expires in one hour."
            : "Enter the email tied to your Meli account and we'll send a reset link."
        }
        footer={
          <AuthLinkRow
            question="Remembered it?"
            href="/sign-in"
            cta="Back to sign in"
          />
        }
      >
        {sent ? (
          <div className="rounded-[var(--radius-lg)] border border-[var(--color-primary-muted)] bg-[var(--color-primary-light)]/60 px-4 py-3 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
            Open the message and follow the link to choose a new password.
            You can close this tab.
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <TextField
              ref={emailRef}
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              inputMode="email"
              required
              placeholder="you@connect.ust.hk"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                if (errors.email)
                  setErrors((prev) => ({ ...prev, email: undefined }));
              }}
              error={errors.email ?? null}
            />

            {errors.form ? (
              <p
                role="alert"
                aria-live="polite"
                className="rounded-[var(--radius-md)] border border-[var(--color-error)]/40 bg-[var(--color-error-light)] px-3 py-2 text-[13px] leading-snug text-[var(--color-error)]"
              >
                {errors.form}
              </p>
            ) : null}

            <PrimaryButton type="submit" loading={busy}>
              Send reset link
            </PrimaryButton>
          </form>
        )}
      </AuthCard>
    </AuthShell>
  );
}
