"use client";

import { toast } from "sonner";

import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  useMe,
  useUpdateNotificationPrefs,
  type NotificationPrefKey,
} from "@/hooks/use-me";
import { cn } from "@/lib/utils";

interface PrefItem {
  readonly key: NotificationPrefKey;
  readonly label: string;
  readonly description: string;
}

/**
 * The five whitelisted notification preferences. New accounts have no stored
 * value for a key, in which case it is treated as enabled (opt-out model).
 */
const PREF_ITEMS: readonly PrefItem[] = [
  {
    key: "checkpoint_published",
    label: "Checkpoint published",
    description: "When your instructor releases a new checkpoint to work through.",
  },
  {
    key: "report_ready",
    label: "Report ready",
    description: "When a progress or evidence report is compiled and ready to read.",
  },
  {
    key: "follow_up_assigned",
    label: "Follow-up assigned",
    description: "When an instructor assigns you a follow-up task after a review.",
  },
  {
    key: "quiz_due_soon",
    label: "Quiz due soon",
    description: "A reminder shortly before a quiz or practice set is due.",
  },
  {
    key: "weekly_summary",
    label: "Weekly summary",
    description: "A once-a-week digest of your activity and what's coming up.",
  },
];

export function NotificationPreferencesForm() {
  const { data: me, isLoading, isError, refetch } = useMe();
  const mutation = useUpdateNotificationPrefs();

  if (isLoading) {
    return <NotificationSkeleton />;
  }

  if (isError || !me) {
    return (
      <StateBanner
        tone="blocked"
        title="Couldn't load your preferences"
        reason="We couldn't reach your account settings. Check your connection and try again."
        action={
          <button
            type="button"
            onClick={() => void refetch()}
            className="rounded-[var(--radius-pill)] bg-[var(--color-text)] px-4 py-1.5 text-xs font-semibold text-[var(--color-surface)]"
          >
            Retry
          </button>
        }
      />
    );
  }

  const prefs = me.notification_prefs ?? {};

  const onToggle = (key: NotificationPrefKey, next: boolean) => {
    mutation.mutate(
      { [key]: next },
      {
        onError: () =>
          toast.error("Couldn't save that preference. Please try again."),
      },
    );
  };

  return (
    <section className="rounded-[var(--radius-2xl)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-sm)]">
      <div className="border-b border-[var(--color-border)]/70 px-6 py-5 sm:px-8">
        <h2 className="text-[16px] font-semibold tracking-tight text-[var(--color-text)]">
          Email &amp; in-app alerts
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          Choose which reminders reach you. Changes save automatically.
        </p>
      </div>

      <ul className="divide-y divide-[var(--color-border)]/60">
        {PREF_ITEMS.map((item) => {
          // Absent key => enabled by default (opt-out model).
          const enabled = prefs[item.key] ?? true;
          const labelId = `notif-${item.key}-label`;
          const descId = `notif-${item.key}-desc`;
          return (
            <li
              key={item.key}
              className="flex items-start justify-between gap-4 px-6 py-4 sm:px-8"
            >
              <div className="min-w-0 space-y-0.5">
                <p
                  id={labelId}
                  className="text-[14px] font-medium text-[var(--color-text)]"
                >
                  {item.label}
                </p>
                <p
                  id={descId}
                  className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]"
                >
                  {item.description}
                </p>
              </div>
              <Switch
                checked={enabled}
                onCheckedChange={(next) => onToggle(item.key, next)}
                disabled={mutation.isPending}
                aria-labelledby={labelId}
                aria-describedby={descId}
                className="mt-0.5"
              />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function NotificationSkeleton() {
  return (
    <section
      className={cn(
        "rounded-[var(--radius-2xl)] border border-[var(--color-border)]",
        "bg-[var(--color-surface)] shadow-[var(--shadow-sm)]",
      )}
    >
      <div className="border-b border-[var(--color-border)]/70 px-6 py-5 sm:px-8">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="mt-2 h-4 w-72" />
      </div>
      <ul className="divide-y divide-[var(--color-border)]/60">
        {Array.from({ length: 5 }).map((_, i) => (
          <li
            key={i}
            className="flex items-center justify-between gap-4 px-6 py-4 sm:px-8"
          >
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3.5 w-64" />
            </div>
            <Skeleton className="h-6 w-11 rounded-full" />
          </li>
        ))}
      </ul>
    </section>
  );
}
