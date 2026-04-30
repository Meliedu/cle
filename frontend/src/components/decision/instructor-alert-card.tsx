"use client";
import { Fragment } from "react";

import type { InstructorAlert } from "@/lib/decision-types";

interface Props {
  readonly alert: InstructorAlert;
  readonly onUpdate: (status: "dismissed" | "resolved") => void;
  readonly busy: boolean;
}

const SEVERITY_BORDER: Record<InstructorAlert["severity"], string> = {
  info: "var(--color-accent)",
  warning: "var(--color-warning)",
  critical: "var(--color-error)",
};

const SEVERITY_BADGE: Record<InstructorAlert["severity"], string> = {
  info: "bg-[var(--color-accent)] text-[var(--color-on-accent)]",
  warning: "bg-[var(--color-warning)] text-[var(--color-text)]",
  critical: "bg-[var(--color-error)] text-[var(--color-on-accent)]",
};

function buildReasonEntries(
  reason: Record<string, unknown>,
): ReadonlyArray<readonly [string, string]> {
  const entries: Array<[string, string]> = [];
  if (typeof reason.concept_name === "string") {
    entries.push(["Concept", reason.concept_name]);
  }
  if (typeof reason.prereq_name === "string") {
    entries.push(["Prereq", reason.prereq_name]);
  }
  if (typeof reason.assignment_id === "string") {
    entries.push(["Assignment", reason.assignment_id.slice(0, 8) + "…"]);
  }
  const enrolled = typeof reason.enrolled === "number" ? reason.enrolled : "?";
  if (typeof reason.weak_n === "number") {
    entries.push(["Weak", `${reason.weak_n}/${enrolled}`]);
  }
  if (typeof reason.attempters === "number") {
    entries.push(["Attempters", `${reason.attempters}/${enrolled}`]);
  }
  if (typeof reason.submitted === "number") {
    entries.push(["Submitted", `${reason.submitted}/${enrolled}`]);
  }
  if (typeof reason.late_count === "number") {
    entries.push(["Late", `${reason.late_count}`]);
  }
  return entries;
}

export function InstructorAlertCard({ alert, onUpdate, busy }: Props) {
  const reasonEntries = buildReasonEntries(alert.reason);
  return (
    <article
      className="space-y-2 rounded border bg-[var(--color-surface)] p-4 transition-colors hover:border-[var(--color-border-hover)]"
      style={{ borderColor: SEVERITY_BORDER[alert.severity] }}
      data-testid="instructor-alert-card"
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {alert.title}
        </h3>
        <span
          className={`rounded-full px-2 py-0.5 text-xs uppercase tracking-wide ${SEVERITY_BADGE[alert.severity]}`}
        >
          {alert.severity}
        </span>
      </header>
      <p className="text-xs text-[var(--color-text-muted)]">
        {alert.alert_type.replaceAll("_", " ")}
      </p>
      {reasonEntries.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-[var(--color-text-muted)]">
          {reasonEntries.map(([k, v]) => (
            <Fragment key={k}>
              <dt>{k}</dt>
              <dd className="text-[var(--color-text)]">{v}</dd>
            </Fragment>
          ))}
        </dl>
      )}
      {alert.status === "open" && (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("dismissed")}
            className="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onUpdate("resolved")}
            className="rounded bg-[var(--color-accent)] px-2 py-1 text-xs text-[var(--color-on-accent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:opacity-50"
          >
            Resolve
          </button>
        </div>
      )}
    </article>
  );
}
