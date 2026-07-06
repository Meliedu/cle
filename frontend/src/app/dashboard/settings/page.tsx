import { SettingsView } from "@/components/settings/settings-view";

export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-10 px-6 pb-24 pt-10 sm:px-8 md:px-12 md:pt-14">
      <header className="space-y-1.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--color-primary-hover)]">
          Account
        </p>
        <h1 className="text-[clamp(1.5rem,1.2rem+1vw,2rem)] font-semibold tracking-tight text-[var(--color-text)]">
          Settings
        </h1>
        <p className="max-w-[58ch] text-[14px] leading-relaxed text-[var(--color-text-secondary)]">
          Update how your name appears across the studio, change your password,
          or close your account.
        </p>
      </header>

      <SettingsView />
    </div>
  );
}
