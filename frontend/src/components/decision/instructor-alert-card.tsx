"use client";
import type { InstructorAlert } from "@/lib/decision-types";

interface Props {
  readonly alert: InstructorAlert;
  readonly onUpdate: (status: "dismissed" | "resolved") => void;
  readonly busy: boolean;
}

const SEVERITY_COLOR: Record<InstructorAlert["severity"], string> = {
  info: "var(--color-accent)",
  warning: "var(--color-warning)",
  critical: "var(--color-error)",
};

export function InstructorAlertCard({ alert, onUpdate, busy }: Props) {
  return (
    <article
      className="space-y-2 rounded border bg-[var(--color-surface)] p-4"
      style={{ borderColor: SEVERITY_COLOR[alert.severity] }}
      data-testid="instructor-alert-card"
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {alert.title}
        </h3>
        <span
          className="text-xs uppercase tracking-wide"
          style={{ color: SEVERITY_COLOR[alert.severity] }}
        >
          {alert.severity}
        </span>
      </header>
      <p className="text-xs text-[var(--color-muted)]">
        {alert.alert_type.replaceAll("_", " ")}
      </p>
      {alert.status === "open" && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("dismissed")}
            className="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("resolved")}
            className="rounded bg-[var(--color-accent)] px-2 py-1 text-xs text-[var(--color-on-accent)] disabled:opacity-50"
          >
            Resolve
          </button>
        </div>
      )}
    </article>
  );
}
