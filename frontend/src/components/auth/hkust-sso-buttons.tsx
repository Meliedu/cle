"use client";

import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";

// providerId "hkust" must match the redirect URI HKUST registered on the app:
// .../api/auth/oauth2/callback/hkust.
export type HkustProviderId = "hkust";

interface HkustSsoButtonsProps {
  readonly onProvider: (providerId: HkustProviderId) => void;
  /** The provider whose OAuth round-trip is currently in flight, if any. */
  readonly pending?: HkustProviderId | null;
  /** Disable the button (e.g. while another auth action runs). */
  readonly disabled?: boolean;
}

interface ButtonSpec {
  readonly id: HkustProviderId;
  readonly label: string;
  readonly hint: string;
}

// One button for everyone: per ITSO the app is multi-tenant (/organizations/),
// so staff (@ust.hk) and students (@connect.ust.hk) sign in through the same
// provider and Microsoft resolves the tenant by email domain.
const BUTTONS: readonly ButtonSpec[] = [
  { id: "hkust", label: "Sign in with HKUST", hint: "@ust.hk / @connect.ust.hk" },
];

/**
 * The two tenant-routing SSO buttons. Presentational only — the page owns the
 * `authClient.signIn.oauth2(...)` call and error surface (mirrors how
 * MicrosoftButton is wired). Rendered by the sign-in page ONLY when
 * NEXT_PUBLIC_HKUST_SSO === "enabled".
 */
export function HkustSsoButtons({
  onProvider,
  pending,
  disabled,
}: HkustSsoButtonsProps) {
  return (
    <div className="grid grid-cols-1 gap-2.5">
      {BUTTONS.map(({ id, label, hint }) => {
        const loading = pending === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onProvider(id)}
            disabled={disabled || Boolean(pending)}
            aria-busy={loading || undefined}
            className={cn(
              "group relative inline-flex h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-md)]",
              "border border-[var(--color-border)] bg-[var(--color-surface)] px-3",
              "text-[13px] font-semibold tracking-[0.01em] text-[var(--color-text)]",
              "outline-none transition-[transform,background-color,border-color,box-shadow] duration-[var(--duration-fast)]",
              "hover:border-[var(--color-border-hover)] hover:bg-[var(--color-surface-hover)]",
              "focus-visible:shadow-[0_0_0_3px_oklch(60%_0.12_230_/_0.32)]",
              "disabled:cursor-not-allowed disabled:opacity-60",
              "motion-safe:active:scale-[0.98]",
            )}
          >
            {loading ? (
              <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            ) : (
              <HkustCrest />
            )}
            <span className="flex flex-col items-start leading-tight">
              <span>{label}</span>
              <span className="text-[10px] font-normal tracking-[0.02em] text-[var(--color-text-muted)]">
                {hint}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Small university-crest glyph in the honey palette; decorative only. */
function HkustCrest() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      role="presentation"
      aria-hidden="true"
      className="shrink-0 text-[var(--color-primary)]"
    >
      <path
        fill="currentColor"
        d="M12 2 3 6v6c0 4.42 3.05 8.52 9 10 5.95-1.48 9-5.58 9-10V6l-9-4Zm0 2.18 7 3.11V12c0 3.5-2.3 6.74-7 8.06C7.3 18.74 5 15.5 5 12V7.29l7-3.11Z"
      />
      <path
        fill="currentColor"
        d="M12 7.5 8.5 9v3c0 2.1 1.4 3.86 3.5 4.6 2.1-.74 3.5-2.5 3.5-4.6V9L12 7.5Z"
        opacity="0.55"
      />
    </svg>
  );
}
