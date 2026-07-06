"use client";

import Link from "next/link";
import { Bell, LogOut, User as UserIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth, useUser } from "@/hooks/use-auth";
import { useRole } from "@/hooks/use-role";
import { cn } from "@/lib/utils";

/**
 * Avatar + popover replacing Clerk's `<UserButton>`. Phase 2.5 will polish
 * styling to Clerk parity (focus rings, motion, accessible menu pattern);
 * this is the minimum viable replacement so the rest of the app compiles
 * and signs out cleanly during the cutover.
 */
export function UserButton() {
  const { user } = useUser();
  const { signOut } = useAuth();
  const { isStudent } = useRole();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  // Link into the caller's role lane. Falls back to the instructor lane while
  // the role is still resolving; both lanes are RoleGate-guarded so a wrong
  // guess redirects rather than 404s.
  const lane = isStudent ? "student" : "teacher";

  useEffect(() => {
    if (!open) return;
    const onDocClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  if (!user) return null;

  const initials = (user.fullName ?? user.primaryEmailAddress?.emailAddress ?? "?")
    .split(/\s+/)
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "flex size-8 items-center justify-center overflow-hidden rounded-full",
          "bg-[var(--color-surface-hover)] text-xs font-semibold text-[var(--color-text)]",
          "outline-none ring-offset-2 ring-offset-[var(--color-surface)]",
          "transition-[box-shadow,transform] duration-[var(--duration-fast)]",
          "hover:scale-105 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]",
        )}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
      >
        {user.imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={user.imageUrl}
            alt=""
            className="size-full object-cover"
          />
        ) : (
          <span aria-hidden>{initials || <UserIcon className="size-4" />}</span>
        )}
      </button>

      {open && (
        <div
          role="menu"
          className={cn(
            "absolute right-0 top-[calc(100%+8px)] z-30 w-56 overflow-hidden rounded-[var(--radius-md)]",
            "border border-[var(--color-border)]/60 bg-[var(--color-surface)] shadow-lg",
          )}
        >
          <div className="px-3 py-2 text-xs">
            <p className="font-medium text-[var(--color-text)]">
              {user.fullName ?? "Signed in"}
            </p>
            <p className="truncate text-[var(--color-text-muted)]">
              {user.primaryEmailAddress?.emailAddress}
            </p>
          </div>
          <div className="h-px bg-[var(--color-border)]/60" />
          <Link
            role="menuitem"
            href={`/${lane}/profile`}
            onClick={() => setOpen(false)}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
              "text-[var(--color-text)] transition-colors duration-[var(--duration-fast)]",
              "hover:bg-[var(--color-surface-hover)] focus-visible:bg-[var(--color-surface-hover)] focus-visible:outline-none",
            )}
          >
            <UserIcon className="size-4" />
            Profile
          </Link>
          <Link
            role="menuitem"
            href={`/${lane}/notifications`}
            onClick={() => setOpen(false)}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
              "text-[var(--color-text)] transition-colors duration-[var(--duration-fast)]",
              "hover:bg-[var(--color-surface-hover)] focus-visible:bg-[var(--color-surface-hover)] focus-visible:outline-none",
            )}
          >
            <Bell className="size-4" />
            Notifications
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={() => {
              setOpen(false);
              void signOut({ redirectUrl: "/sign-in" });
            }}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
              "text-[var(--color-text)] transition-colors duration-[var(--duration-fast)]",
              "hover:bg-[var(--color-surface-hover)] focus-visible:bg-[var(--color-surface-hover)] focus-visible:outline-none",
            )}
          >
            <LogOut className="size-4" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
