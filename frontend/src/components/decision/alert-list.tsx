"use client";
import { useState } from "react";

import { InstructorAlertCard } from "@/components/decision/instructor-alert-card";
import {
  useInstructorAlerts,
  useUpdateInstructorAlert,
} from "@/hooks/use-instructor-alerts";
import type { AlertStatus } from "@/lib/decision-types";

interface Props {
  readonly courseId: string;
}

const TABS: AlertStatus[] = ["open", "dismissed", "resolved"];

export function AlertList({ courseId }: Props) {
  const [status, setStatus] = useState<AlertStatus>("open");
  const { data, isLoading, error } = useInstructorAlerts(courseId, status);
  const update = useUpdateInstructorAlert(courseId);

  const tabs = TABS.map((s) => (
    <button
      key={s}
      type="button"
      onClick={() => setStatus(s)}
      className={
        "rounded px-3 py-1 text-xs " +
        (status === s
          ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
          : "text-[var(--color-muted)] hover:text-[var(--color-text)]")
      }
    >
      {s}
    </button>
  ));

  return (
    <section className="space-y-3">
      <nav className="flex gap-2">{tabs}</nav>
      {isLoading && <p className="text-sm text-[var(--color-muted)]">Loading…</p>}
      {error && <p className="text-sm text-[var(--color-error)]">Failed to load.</p>}
      {!isLoading && (data ?? []).length === 0 && (
        <p className="text-sm text-[var(--color-muted)]">
          Nothing here. ({status})
        </p>
      )}
      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(data ?? []).map((a) => (
          <li key={a.id}>
            <InstructorAlertCard
              alert={a}
              busy={update.isPending}
              onUpdate={(s) => update.mutate({ alertId: a.id, status: s })}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
