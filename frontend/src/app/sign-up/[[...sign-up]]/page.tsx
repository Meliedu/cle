"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";
import { DividerLabel } from "@/components/auth/divider-label";
import { MicrosoftButton } from "@/components/auth/microsoft-button";
import {
  PasswordStrengthMeter,
} from "@/components/auth/password-strength-meter";
import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { authClient } from "@/lib/auth-client";
import { isEmailPasswordHost } from "@/lib/auth-flags";
import { ALLOWED_DOMAINS } from "@/lib/auth-domain";

const MICROSOFT_SSO_ENABLED =
  process.env.NEXT_PUBLIC_MICROSOFT_SSO_ENABLED === "true";

const MIN_PASSWORD = 8;

interface FieldErrors {
  name?: string;
  email?: string;
  password?: string;
  form?: string;
}

function validateDomain(email: string): string | undefined {
  const lower = email.trim().toLowerCase();
  const at = lower.lastIndexOf("@");
  if (at === -1) return "Enter a valid email address.";
  const domain = lower.slice(at + 1);
  if (!ALLOWED_DOMAINS.includes(domain)) {
    return `Only ${ALLOWED_DOMAINS.map((d) => `@${d}`).join(" / ")} accepted.`;
  }
  return undefined;
}

export default function SignUpPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [microsoftBusy, setMicrosoftBusy] = useState(false);

  const nameRef = useRef<HTMLInputElement | null>(null);
  const emailRef = useRef<HTMLInputElement | null>(null);
  const passwordRef = useRef<HTMLInputElement | null>(null);

  // Host-gated like sign-in. `null` = not yet resolved (needs the real
  // hostname, only available after mount). SSO-only environments (production)
  // have no email/password sign-up, so send people to /sign-in — it hosts the
  // SSO buttons and auto-provisions the account on first login.
  const [emailEnabled, setEmailEnabled] = useState<boolean | null>(null);
  useEffect(() => {
    const ok = isEmailPasswordHost(window.location.hostname);
    setEmailEnabled(ok);
    if (!ok) router.replace("/sign-in");
  }, [router]);

  const onMicrosoft = async () => {
    setErrors({});
    setMicrosoftBusy(true);
    // Microsoft SSO emails are pre-verified by the IdP so we skip the
    // /verify-email step that the email/password flow goes through. Land
    // straight on the dashboard.
    const { error } = await authClient.signIn.social({
      provider: "microsoft",
      callbackURL: "/dashboard",
    });
    if (error) {
      setErrors({ form: error.message ?? "Microsoft sign-up failed" });
    }
    setMicrosoftBusy(false);
  };

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedEmail = email.trim();

    const next: FieldErrors = {};
    if (!trimmedName) next.name = "Tell us your name.";
    if (!trimmedEmail) next.email = "Email is required.";
    else {
      const domainErr = validateDomain(trimmedEmail);
      if (domainErr) next.email = domainErr;
    }
    if (!password) next.password = "Password is required.";
    else if (password.length < MIN_PASSWORD)
      next.password = `Use at least ${MIN_PASSWORD} characters.`;

    if (Object.keys(next).length > 0) {
      setErrors(next);
      if (next.name) nameRef.current?.focus();
      else if (next.email) emailRef.current?.focus();
      else if (next.password) passwordRef.current?.focus();
      return;
    }

    setErrors({});
    setBusy(true);
    const { error } = await authClient.signUp.email({
      name: trimmedName,
      email: trimmedEmail,
      password,
      callbackURL: "/dashboard",
    });
    if (error) {
      setBusy(false);
      setErrors({ form: error.message ?? "Sign-up failed." });
      passwordRef.current?.focus();
      return;
    }
    router.push("/verify-email");
  };

  const allowedDomainsLabel = ALLOWED_DOMAINS.map((d) => `@${d}`).join(" / ");

  // Render nothing until the host is resolved, or while redirecting away in
  // SSO-only mode.
  if (emailEnabled !== true) return null;

  return (
    <AuthShell tagline="Get started">
      <AuthCard
        eyebrow="New to Meli · HKUST CLE"
        heading="Create your account"
        subtitle={
          <>
            Open to{" "}
            <span className="font-medium text-[var(--color-text)]">
              {allowedDomainsLabel}
            </span>{" "}
            email addresses only.
          </>
        }
        footer={
          <AuthLinkRow
            question="Already have an account?"
            href="/sign-in"
            cta="Sign in"
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
            ref={nameRef}
            label="Full name"
            name="name"
            type="text"
            autoComplete="name"
            required
            placeholder="Your name"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              if (errors.name) setErrors((prev) => ({ ...prev, name: undefined }));
            }}
            error={errors.name ?? null}
          />

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
            onBlur={() => {
              if (!email.trim()) return;
              const err = validateDomain(email);
              if (err) setErrors((prev) => ({ ...prev, email: err }));
            }}
            error={errors.email ?? null}
          />

          <div className="space-y-2">
            <TextField
              ref={passwordRef}
              label="Password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              placeholder={`At least ${MIN_PASSWORD} characters`}
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                if (errors.password)
                  setErrors((prev) => ({ ...prev, password: undefined }));
              }}
              error={errors.password ?? null}
            />
            <PasswordStrengthMeter
              password={password}
              minLength={MIN_PASSWORD}
            />
          </div>

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
            Create account
          </PrimaryButton>
        </form>
      </AuthCard>
    </AuthShell>
  );
}
