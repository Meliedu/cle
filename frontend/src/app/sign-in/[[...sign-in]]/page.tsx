"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";
import { DividerLabel } from "@/components/auth/divider-label";
import {
  HkustSsoButtons,
  type HkustProviderId,
} from "@/components/auth/hkust-sso-buttons";
import { MicrosoftButton } from "@/components/auth/microsoft-button";
import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { authClient } from "@/lib/auth-client";
import { isEmailPasswordHost } from "@/lib/auth-flags";
import { sanitizeRedirect } from "@/lib/redirect";

const MICROSOFT_SSO_ENABLED =
  process.env.NEXT_PUBLIC_MICROSOFT_SSO_ENABLED === "true";

// HKUST OIDC (staff + student Entra tenants) is a pure env-flag drop: the two
// tenant buttons only appear when the flag is "enabled" AND the backend
// providers are configured (src/lib/auth.ts). Unset today → dormant.
const HKUST_SSO_ENABLED = process.env.NEXT_PUBLIC_HKUST_SSO === "enabled";

interface FieldErrors {
  email?: string;
  password?: string;
  form?: string;
}

export default function SignInPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Only accept internal redirects — see sanitizeRedirect for the threat
  // model (absolute URLs, protocol-relative "//", and backslash "/\" escapes
  // all fall back to /dashboard).
  const redirectTo = sanitizeRedirect(searchParams.get("redirect"));

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);
  const [microsoftBusy, setMicrosoftBusy] = useState(false);
  const [hkustPending, setHkustPending] = useState<HkustProviderId | null>(null);
  // Email/password is host-gated: on only for the dev domain + localhost, off
  // for the SSO-only production host. Resolved after mount (needs the real
  // hostname); defaults to off so production never flashes the credential form.
  const [emailEnabled, setEmailEnabled] = useState(false);
  useEffect(() => {
    setEmailEnabled(isEmailPasswordHost(window.location.hostname));
  }, []);

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

  const onHkust = async (providerId: HkustProviderId) => {
    setErrors({});
    setHkustPending(providerId);
    try {
      // Same generic-OAuth entry as any provider: better-auth redirects the
      // browser to the tenant's Entra authorize endpoint and returns to
      // /api/auth/oauth2/callback/{providerId}, then to callbackURL.
      const { error } = await authClient.signIn.oauth2({
        providerId,
        callbackURL: redirectTo,
      });
      if (error) {
        setErrors({ form: error.message ?? "HKUST sign-in failed" });
        setHkustPending(null);
      }
      // On success the browser is navigating away; keep the spinner up.
    } catch {
      setErrors({ form: "Couldn't reach the HKUST sign-in service. Try again." });
      setHkustPending(null);
    }
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
    try {
      const { data, error } = await authClient.signIn.email({
        email: trimmedEmail,
        password,
        callbackURL: redirectTo,
      });
      if (error || !data?.user) {
        setBusy(false);
        // Always return a generic message — distinguishing "no such user" from
        // "wrong password" leaks whether an email is registered.
        setErrors({ form: "Invalid email or password." });
        passwordRef.current?.focus();
        return;
      }
      router.push(redirectTo);
    } catch {
      // Network or runtime failure (CORS, mixed-content, fetch abort, …).
      // Keep the user on the page with a visible error rather than letting
      // the spinner hang forever.
      setBusy(false);
      setErrors({ form: "Couldn't reach the sign-in service. Try again." });
    }
  };

  return (
    <AuthShell tagline="Welcome back">
      <AuthCard
        eyebrow="Welcome back · HKUST CLE"
        heading="Sign in to Meli"
        subtitle="Pick up your courses, checkpoints, and this week's next steps."
        footer={
          // Manual account creation only exists on the email/password path;
          // SSO-only environments auto-provision on first login.
          emailEnabled ? (
            <AuthLinkRow
              question="New here?"
              href="/sign-up"
              cta="Create an account"
            />
          ) : undefined
        }
      >
        {HKUST_SSO_ENABLED || MICROSOFT_SSO_ENABLED ? (
          <div className="space-y-3">
            {HKUST_SSO_ENABLED ? (
              <div className="space-y-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-muted)]">
                  Sign in with HKUST
                </p>
                <HkustSsoButtons
                  onProvider={onHkust}
                  pending={hkustPending}
                  disabled={busy || microsoftBusy}
                />
              </div>
            ) : null}

            {MICROSOFT_SSO_ENABLED ? (
              <MicrosoftButton
                onClick={onMicrosoft}
                loading={microsoftBusy}
                disabled={busy || Boolean(hkustPending)}
              />
            ) : null}
          </div>
        ) : null}

        {/* The divider only belongs between two real methods. */}
        {(HKUST_SSO_ENABLED || MICROSOFT_SSO_ENABLED) && emailEnabled ? (
          <DividerLabel label="or with email" />
        ) : null}

        {emailEnabled ? (
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
        ) : null}
      </AuthCard>
    </AuthShell>
  );
}
