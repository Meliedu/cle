"use client";

import { useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";
import { DividerLabel } from "@/components/auth/divider-label";
import { MicrosoftButton } from "@/components/auth/microsoft-button";
import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { authClient } from "@/lib/auth-client";

const MICROSOFT_SSO_ENABLED =
  process.env.NEXT_PUBLIC_MICROSOFT_SSO_ENABLED === "true";

interface FieldErrors {
  email?: string;
  password?: string;
  form?: string;
}

export default function SignInPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Only accept internal redirects. Reject "//evil.com" (protocol-relative)
  // and any absolute URL — both can be exploited as open redirects.
  const rawRedirect = searchParams.get("redirect") ?? "/dashboard";
  const redirectTo =
    rawRedirect.startsWith("/") && !rawRedirect.startsWith("//")
      ? rawRedirect
      : "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [microsoftBusy, setMicrosoftBusy] = useState(false);

  const emailRef = useRef<HTMLInputElement | null>(null);
  const passwordRef = useRef<HTMLInputElement | null>(null);

  const onMicrosoft = async () => {
    setErrors({});
    setMicrosoftBusy(true);
    const { error } = await authClient.signIn.social({
      provider: "microsoft",
      callbackURL: redirectTo,
    });
    if (error) {
      setErrors({ form: error.message ?? "Microsoft sign-in failed" });
    }
    setMicrosoftBusy(false);
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedEmail = email.trim();
    const next: FieldErrors = {};
    if (!trimmedEmail) next.email = "Email is required.";
    else if (!/.+@.+\..+/.test(trimmedEmail)) next.email = "Enter a valid email address.";
    if (!password) next.password = "Password is required.";
    if (Object.keys(next).length > 0) {
      setErrors(next);
      if (next.email) emailRef.current?.focus();
      else if (next.password) passwordRef.current?.focus();
      return;
    }

    setErrors({});
    setBusy(true);
    const { error } = await authClient.signIn.email({
      email: trimmedEmail,
      password,
      callbackURL: redirectTo,
    });
    if (error) {
      setBusy(false);
      setErrors({
        form:
          error.message === "User not found"
            ? "No account matches that email."
            : (error.message ?? "Sign-in failed."),
      });
      passwordRef.current?.focus();
      return;
    }
    router.push(redirectTo);
  };

  return (
    <AuthShell tagline="Sign in to your studio">
      <AuthCard
        eyebrow="Welcome back · HKUST"
        heading="Sign in to Meli"
        subtitle="Pick up your courses, materials, and AI-generated study sets."
        footer={
          <AuthLinkRow
            question="New here?"
            href="/sign-up"
            cta="Create an account"
          />
        }
      >
        {MICROSOFT_SSO_ENABLED ? (
          <>
            <MicrosoftButton
              onClick={onMicrosoft}
              loading={microsoftBusy}
              disabled={busy}
            />
            <DividerLabel label="or with email" />
          </>
        ) : null}

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
              if (errors.email) setErrors((prev) => ({ ...prev, email: undefined }));
            }}
            error={errors.email ?? null}
          />

          <TextField
            ref={passwordRef}
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            placeholder="••••••••••"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              if (errors.password)
                setErrors((prev) => ({ ...prev, password: undefined }));
            }}
            error={errors.password ?? null}
            helperText={
              <a
                href="/forgot-password"
                className="text-[11px] font-medium text-[var(--color-accent-hover)] underline-offset-[3px] hover:underline focus-visible:underline focus-visible:outline-none"
              >
                Forgot password?
              </a>
            }
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
            Sign in
          </PrimaryButton>
        </form>
      </AuthCard>
    </AuthShell>
  );
}
