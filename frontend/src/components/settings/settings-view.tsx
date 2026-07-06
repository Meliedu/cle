"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, Check, Loader2, Trash2 } from "lucide-react";

import { PrimaryButton } from "@/components/auth/auth-buttons";
import { TextField } from "@/components/auth/text-field";
import { PasswordStrengthMeter } from "@/components/auth/password-strength-meter";
import { authClient } from "@/lib/auth-client";
import { useUser } from "@/hooks/use-auth";
import { useRole } from "@/hooks/use-role";
import { cn } from "@/lib/utils";

const MIN_PASSWORD = 8;
const DELETE_PHRASE = "delete my account";

/**
 * Account settings composition shared by every role lane
 * (`/teacher/profile`, `/student/profile`) and the legacy `/dashboard/settings`
 * route. Renders the profile, security, and danger sections as a vertical
 * stack; the page wrapping this view owns its own heading (a `PageHeader`
 * "Profile" in the lane routes, the bespoke "Settings" header on the legacy
 * route).
 */
export function SettingsView() {
  return (
    <div className="space-y-10">
      <ProfileSection />
      <SecuritySection />
      <DangerSection />
    </div>
  );
}

function SectionShell({
  eyebrow,
  title,
  description,
  children,
  tone = "default",
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
  tone?: "default" | "danger";
}) {
  return (
    <section
      className={cn(
        "grid grid-cols-1 gap-7 rounded-[var(--radius-2xl)] border bg-[var(--color-surface)] p-7 shadow-[var(--shadow-sm)] sm:p-8 md:grid-cols-[minmax(0,18rem),minmax(0,1fr)] md:gap-12 md:p-10 lg:p-12",
        tone === "danger"
          ? "border-[var(--color-error)]/35"
          : "border-[var(--color-border)]",
      )}
    >
      <div className="space-y-2">
        <p
          className={cn(
            "text-[11px] font-semibold uppercase tracking-[0.22em]",
            tone === "danger"
              ? "text-[var(--color-error)]"
              : "text-[var(--color-primary-hover)]",
          )}
        >
          {eyebrow}
        </p>
        <h2 className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
          {title}
        </h2>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {description}
        </p>
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function ProfileSection() {
  const { user, isLoaded } = useUser();
  const [name, setName] = useState("");
  const [pristine, setPristine] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement | null>(null);
  const [syncedName, setSyncedName] = useState<string | null>(null);

  // Seed the editable name from the loaded profile once (and again if the
  // upstream name changes). Syncing during render via a "previous value" state
  // — rather than in an effect — avoids the extra commit + cascading-render
  // lint while staying correct.
  if (
    user?.fullName !== undefined &&
    user?.fullName !== null &&
    user.fullName !== syncedName
  ) {
    setSyncedName(user.fullName);
    setName(user.fullName);
    setPristine(user.fullName);
  }

  const dirty = name.trim() !== pristine.trim();

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Name cannot be empty.");
      nameRef.current?.focus();
      return;
    }
    setError(null);
    setBusy(true);
    const { error } = await authClient.updateUser({ name: trimmed });
    setBusy(false);
    if (error) {
      setError(error.message ?? "Could not update profile.");
      return;
    }
    setPristine(trimmed);
    toast.success("Profile updated.");
  };

  return (
    <SectionShell
      eyebrow="Profile"
      title="Your details"
      description="Your name appears on shared materials and live-quiz leaderboards. Email and role come from your HKUST account and can't be changed here."
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <TextField
          ref={nameRef}
          label="Display name"
          name="name"
          autoComplete="name"
          required
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            if (error) setError(null);
          }}
          disabled={!isLoaded || busy}
          error={error}
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <ReadOnlyField label="Email" value={user?.primaryEmailAddress?.emailAddress ?? "—"} />
          <ReadOnlyField label="Role" value={<RoleBadge />} />
        </div>

        <div className="flex justify-end">
          <PrimaryButton
            type="submit"
            disabled={!dirty}
            loading={busy}
            className="!w-auto px-6"
          >
            Save changes
          </PrimaryButton>
        </div>
      </form>
    </SectionShell>
  );
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-[12px] font-medium tracking-[0.04em] text-[var(--color-text-secondary)]">
        {label}
      </p>
      <div className="flex h-11 items-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3.5 text-[14px] text-[var(--color-text)]">
        {value}
      </div>
    </div>
  );
}

function RoleBadge() {
  // Reads the authoritative stored role from the backend /api/auth/me
  // endpoint via useRole, so it stays correct even if the user's email
  // domain ↔ role mapping has drifted.
  const { isInstructor, isStudent, isLoaded } = useRole();
  const label = !isLoaded
    ? "—"
    : isInstructor
      ? "Instructor"
      : isStudent
        ? "Student"
        : "Member";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-1.5 rounded-full bg-[var(--color-primary)]" aria-hidden="true" />
      {label}
    </span>
  );
}

function SecuritySection() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [revokeOthers, setRevokeOthers] = useState(true);
  const [errors, setErrors] = useState<{
    current?: string;
    next?: string;
    confirm?: string;
    form?: string;
  }>({});
  const [busy, setBusy] = useState(false);

  const currentRef = useRef<HTMLInputElement | null>(null);
  const nextRef = useRef<HTMLInputElement | null>(null);
  const confirmRef = useRef<HTMLInputElement | null>(null);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next_errors: typeof errors = {};
    if (!current) next_errors.current = "Enter your current password.";
    if (!next) next_errors.next = "Enter a new password.";
    else if (next.length < MIN_PASSWORD)
      next_errors.next = `Use at least ${MIN_PASSWORD} characters.`;
    if (next !== confirm) next_errors.confirm = "Passwords do not match.";

    if (Object.keys(next_errors).length > 0) {
      setErrors(next_errors);
      if (next_errors.current) currentRef.current?.focus();
      else if (next_errors.next) nextRef.current?.focus();
      else if (next_errors.confirm) confirmRef.current?.focus();
      return;
    }

    setErrors({});
    setBusy(true);
    const { error } = await authClient.changePassword({
      currentPassword: current,
      newPassword: next,
      revokeOtherSessions: revokeOthers,
    });
    setBusy(false);
    if (error) {
      setErrors({
        form:
          error.message === "Invalid password"
            ? "Current password is incorrect."
            : (error.message ?? "Could not update password."),
      });
      currentRef.current?.focus();
      return;
    }
    setCurrent("");
    setNext("");
    setConfirm("");
    toast.success(
      revokeOthers
        ? "Password updated. Other sessions signed out."
        : "Password updated.",
    );
  };

  return (
    <SectionShell
      eyebrow="Security"
      title="Change password"
      description="Use a phrase you don't reuse elsewhere. Optionally sign out of every other device when you save."
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <TextField
          ref={currentRef}
          label="Current password"
          name="current-password"
          type="password"
          autoComplete="current-password"
          required
          value={current}
          onChange={(event) => {
            setCurrent(event.target.value);
            if (errors.current) setErrors((p) => ({ ...p, current: undefined }));
          }}
          error={errors.current ?? null}
        />

        <div className="space-y-2">
          <TextField
            ref={nextRef}
            label="New password"
            name="new-password"
            type="password"
            autoComplete="new-password"
            required
            placeholder={`At least ${MIN_PASSWORD} characters`}
            value={next}
            onChange={(event) => {
              setNext(event.target.value);
              if (errors.next) setErrors((p) => ({ ...p, next: undefined }));
            }}
            error={errors.next ?? null}
          />
          <PasswordStrengthMeter password={next} minLength={MIN_PASSWORD} />
        </div>

        <TextField
          ref={confirmRef}
          label="Confirm new password"
          name="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(event) => {
            setConfirm(event.target.value);
            if (errors.confirm) setErrors((p) => ({ ...p, confirm: undefined }));
          }}
          error={errors.confirm ?? null}
        />

        <label className="flex cursor-pointer items-start gap-2.5 text-[13px] text-[var(--color-text-secondary)]">
          <input
            type="checkbox"
            checked={revokeOthers}
            onChange={(event) => setRevokeOthers(event.target.checked)}
            className="mt-0.5 size-4 cursor-pointer rounded border-[var(--color-border)] text-[var(--color-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2"
          />
          <span>
            Sign out of all other sessions on save
            <span className="block text-[11px] text-[var(--color-text-muted)]">
              Recommended if you suspect someone else used your account.
            </span>
          </span>
        </label>

        {errors.form ? (
          <p
            role="alert"
            aria-live="polite"
            className="rounded-[var(--radius-md)] border border-[var(--color-error)]/40 bg-[var(--color-error-light)] px-3 py-2 text-[13px] leading-snug text-[var(--color-error)]"
          >
            {errors.form}
          </p>
        ) : null}

        <div className="flex justify-end">
          <PrimaryButton type="submit" loading={busy} className="!w-auto px-6">
            Update password
          </PrimaryButton>
        </div>
      </form>
    </SectionShell>
  );
}

function DangerSection() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const phraseRef = useRef<HTMLInputElement | null>(null);

  const onConfirm = async () => {
    if (phrase.trim().toLowerCase() !== DELETE_PHRASE) {
      setError(`Type "${DELETE_PHRASE}" exactly to confirm.`);
      phraseRef.current?.focus();
      return;
    }
    setError(null);
    setBusy(true);
    const { error: deleteError } = await authClient.deleteUser();
    setBusy(false);
    if (deleteError) {
      const message = deleteError.message ?? "Account deletion failed.";
      // Surface the structured "still owns courses" hint our backend
      // returns when an instructor tries to delete a populated account.
      if (message.includes("HAS_INSTRUCTOR_CONTENT") || message.includes("course")) {
        setError(
          "This account still owns courses or uploaded materials. Transfer or remove them first, or contact support.",
        );
        return;
      }
      setError(message);
      return;
    }
    toast.success("Your account was deleted.");
    setOpen(false);
    router.push("/sign-in");
  };

  return (
    <SectionShell
      eyebrow="Danger zone"
      title="Delete account"
      description="This permanently removes your sign-in, study history, flashcards, and quiz attempts. Course ownership and uploaded materials must be removed first."
      tone="danger"
    >
      {!open ? (
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3 text-[13px] text-[var(--color-text-secondary)]">
            <AlertTriangle
              className="mt-0.5 size-4 shrink-0 text-[var(--color-error)]"
              aria-hidden="true"
            />
            <span>This cannot be undone.</span>
          </div>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className={cn(
              "inline-flex h-10 items-center justify-center gap-2 rounded-[var(--radius-md)]",
              "border border-[var(--color-error)]/50 px-4 text-[13px] font-semibold text-[var(--color-error)]",
              "transition-[background-color,border-color,box-shadow] duration-[var(--duration-fast)]",
              "hover:bg-[var(--color-error-light)] hover:border-[var(--color-error)]",
              "focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_oklch(55%_0.22_25_/_0.25)]",
            )}
          >
            <Trash2 className="size-4" aria-hidden="true" />
            Delete account
          </button>
        </div>
      ) : (
        <div className="space-y-4 rounded-[var(--radius-md)] border border-[var(--color-error)]/40 bg-[var(--color-error-light)] p-4">
          <div className="space-y-1.5">
            <p className="flex items-center gap-2 text-[13px] font-semibold text-[var(--color-error)]">
              <AlertTriangle className="size-4" aria-hidden="true" />
              Confirm deletion
            </p>
            <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
              Type <code className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 font-mono text-[12px]">{DELETE_PHRASE}</code> to confirm. We&apos;ll sign you out and remove your account immediately.
            </p>
          </div>

          <TextField
            ref={phraseRef}
            label="Confirmation phrase"
            name="delete-confirm"
            value={phrase}
            onChange={(event) => {
              setPhrase(event.target.value);
              if (error) setError(null);
            }}
            error={error}
            autoComplete="off"
            placeholder={DELETE_PHRASE}
          />

          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                setPhrase("");
                setError(null);
              }}
              disabled={busy}
              className="inline-flex h-10 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-4 text-[13px] font-semibold text-[var(--color-text)] transition-colors duration-[var(--duration-fast)] hover:bg-[var(--color-surface-hover)] disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              disabled={busy}
              aria-busy={busy || undefined}
              className={cn(
                "inline-flex h-10 items-center justify-center gap-2 rounded-[var(--radius-md)] px-4 text-[13px] font-semibold",
                "bg-[var(--color-error)] text-white shadow-[var(--shadow-sm)]",
                "transition-[background-color,box-shadow,transform] duration-[var(--duration-fast)]",
                "hover:bg-[oklch(48%_0.22_25)] motion-safe:active:scale-[0.98]",
                "focus-visible:outline-none focus-visible:shadow-[0_0_0_3px_oklch(55%_0.22_25_/_0.32)]",
                "disabled:cursor-not-allowed disabled:opacity-60",
              )}
            >
              {busy ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Check className="size-4" aria-hidden="true" />
              )}
              Permanently delete
            </button>
          </div>
        </div>
      )}
    </SectionShell>
  );
}
