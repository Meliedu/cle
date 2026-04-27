"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

interface PasswordStrengthMeterProps {
  readonly password: string;
  readonly minLength?: number;
}

type Tier = 0 | 1 | 2 | 3 | 4;

interface Score {
  readonly tier: Tier;
  readonly label: string;
}

function score(password: string, minLength: number): Score {
  if (!password) return { tier: 0, label: "Enter a password" };
  if (password.length < minLength) return { tier: 0, label: "Too short" };

  // From here we know the password meets the minimum length; classify
  // strength purely on character variety + extra length.
  let bits = 1;
  if (password.length >= minLength + 4) bits += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) bits += 1;
  if (/\d/.test(password)) bits += 1;
  if (/[^A-Za-z0-9]/.test(password)) bits += 1;

  const tier = Math.min(4, bits) as Tier;
  const label =
    tier === 1 ? "Weak" : tier === 2 ? "Fair" : tier === 3 ? "Good" : "Strong";
  return { tier, label };
}

const SEGMENT_COLORS: readonly string[] = [
  "var(--color-error)",
  "var(--color-warning)",
  "var(--color-warning)",
  "var(--color-success)",
];

/**
 * Four-segment password strength meter. Updates 150ms after the last
 * keystroke (debounced) so the UI doesn't flash with every character.
 */
export function PasswordStrengthMeter({
  password,
  minLength = 8,
}: PasswordStrengthMeterProps) {
  const [debounced, setDebounced] = useState(password);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(password), 150);
    return () => window.clearTimeout(handle);
  }, [password]);

  const { tier, label } = score(debounced, minLength);

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={`Password strength: ${label}`}
      className="space-y-1.5"
    >
      <div className="flex gap-1.5">
        {[0, 1, 2, 3].map((index) => {
          const filled = tier > index;
          const color =
            SEGMENT_COLORS[Math.min(SEGMENT_COLORS.length - 1, Math.max(0, tier - 1))];
          return (
            <span
              key={index}
              className={cn(
                "h-1 flex-1 rounded-full transition-[background-color,opacity] duration-[var(--duration-normal)]",
              )}
              style={{
                backgroundColor: filled ? color : "var(--color-border)",
                opacity: filled ? 1 : 0.6,
              }}
            />
          );
        })}
      </div>
      <p className="text-[11px] tracking-[0.02em] text-[var(--color-text-muted)]">
        {label}
      </p>
    </div>
  );
}
