"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { AuthCard } from "@/components/auth/auth-card";
import { AuthLinkRow } from "@/components/auth/auth-link-row";
import { AuthShell } from "@/components/auth/auth-shell";
import {
  PasswordStrengthMeter,
} from "@/components/auth/password-strength-meter";
import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { authClient } from "@/lib/auth-client";
import { isEmailPasswordHost } from "@/lib/auth-flags";

const MIN_PASSWORD = 8;

interface FieldErrors {
  password?: string;
  confirm?: string;
  form?: string;
}

export default function ResetPasswordPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const tokenError = searchParams.get("error");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [busy, setBusy] = useState(false);

  const passwordRef = useRef<HTMLInputElement | null>(null);
  const confirmRef = useRef<HTMLInputElement | null>(null);

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
    if (!token) {
      setErrors({ form: "This reset link is invalid or has expired." });
      return;
    }
    const next: FieldErrors = {};
    if (!password) next.password = "Password is required.";
    else if (password.length < MIN_PASSWORD)
      next.password = `Use at least ${MIN_PASSWORD} characters.`;
    if (password !== confirm) next.confirm = "Passwords do not match.";

    if (Object.keys(next).length > 0) {
      setErrors(next);
      if (next.password) passwordRef.current?.focus();
      else if (next.confirm) confirmRef.current?.focus();
      return;
    }

    setErrors({});
    setBusy(true);
    const { error } = await authClient.resetPassword({
      newPassword: password,
      token,
    });
    setBusy(false);
    if (error) {
      setErrors({ form: error.message ?? "Could not reset password." });
      return;
    }
    toast.success("Password updated. Sign in with your new password.");
    router.push("/sign-in?reset=1");
  };

  const linkInvalid = !token || tokenError === "INVALID_TOKEN";

  // Nothing renders until the host check resolves (and never on SSO-only
  // hosts, which are already being redirected).
  if (!allowed) return null;

  return (
    <AuthShell tagline="New password">
      <AuthCard
        eyebrow="Reset password"
        heading={linkInvalid ? "This link expired" : "Choose a new password"}
        subtitle={
          linkInvalid
            ? "Reset links are good for one hour. Request a fresh one and we'll send it right over."
            : `Pick something memorable but uncommon — at least ${MIN_PASSWORD} characters.`
        }
        footer={
          <AuthLinkRow
            question={linkInvalid ? "Need a new link?" : "Changed your mind?"}
            href={linkInvalid ? "/forgot-password" : "/sign-in"}
            cta={linkInvalid ? "Request reset" : "Back to sign in"}
          />
        }
      >
        {linkInvalid ? (
          <p className="rounded-[var(--radius-md)] border border-[var(--color-warning)]/40 bg-[var(--color-warning-light)] px-3 py-2 text-[13px] leading-snug text-[var(--color-text-secondary)]">
            For your security, the link can only be used once. Request a new
            one from the sign-in screen.
          </p>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-2">
              <TextField
                ref={passwordRef}
                label="New password"
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

            <TextField
              ref={confirmRef}
              label="Confirm password"
              name="confirm"
              type="password"
              autoComplete="new-password"
              required
              placeholder="Re-enter your password"
              value={confirm}
              onChange={(event) => {
                setConfirm(event.target.value);
                if (errors.confirm)
                  setErrors((prev) => ({ ...prev, confirm: undefined }));
              }}
              error={errors.confirm ?? null}
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
              Update password
            </PrimaryButton>
          </form>
        )}
      </AuthCard>
    </AuthShell>
  );
}
