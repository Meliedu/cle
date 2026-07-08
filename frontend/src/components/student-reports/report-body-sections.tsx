"use client";

import {
  CheckCircle2,
  ListChecks,
  Sparkles,
  Target,
  type LucideIcon,
} from "lucide-react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import type { ReportBody, ReportWeakPoint } from "@/hooks/use-reports";

/**
 * Renders the typed report `body` sections (S067 weekly / S068 end-term). Every
 * section is composed by the backend from REVIEWED evidence only, so this is a
 * pure presenter — it shows a section only when its evidence is present and
 * never fabricates a placeholder (an empty observations list simply omits the
 * "what improved" card). Weekly and end-term reports share the same body shape;
 * the two screens differ only in which sections tend to be populated.
 */
interface ReportBodySectionsProps {
  readonly body: ReportBody;
}

export function ReportBodySections({ body }: ReportBodySectionsProps) {
  const t = useTranslations("student.reports.body");
  const hasObservations = body.observations.length > 0;
  const hasWeakPoints = body.weak_points.length > 0;
  const hasNextActions = body.next_actions.length > 0;

  return (
    <div className="space-y-4">
      {body.summary.trim() ? (
        <p className="text-[15px] leading-relaxed text-[var(--color-text)]">
          {body.summary}
        </p>
      ) : null}

      <CompletedWorkStat count={body.completed_work.completed_count} />

      {hasObservations ? (
        <Section icon={Sparkles} title={t("observations")}>
          <ul className="space-y-2">
            {body.observations.map((observation, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-[14px] leading-relaxed text-[var(--color-text-secondary)]"
              >
                <CheckCircle2
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0 text-[var(--color-success)]"
                />
                <span>{observation}</span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {hasWeakPoints ? (
        <Section icon={Target} title={t("weakPoints")}>
          <ul className="space-y-2.5">
            {body.weak_points.map((point) => (
              <WeakPointRow key={point.concept_id} point={point} />
            ))}
          </ul>
        </Section>
      ) : null}

      {hasNextActions ? (
        <Section icon={ListChecks} title={t("nextActions")}>
          <ol className="space-y-2">
            {body.next_actions.map((action, i) => (
              <li
                key={i}
                className="flex items-start gap-3 text-[14px] leading-relaxed text-[var(--color-text)]"
              >
                <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)]/12 text-[11px] font-semibold tabular-nums text-[var(--color-primary-hover)]">
                  {i + 1}
                </span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </Section>
      ) : null}
    </div>
  );
}

/** A titled card wrapping one report section. */
function Section({
  icon: Icon,
  title,
  children,
}: {
  readonly icon: LucideIcon;
  readonly title: string;
  readonly children: ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
        <Icon
          aria-hidden="true"
          className="size-4 text-[var(--color-text-muted)]"
        />
        {title}
      </h2>
      {children}
    </section>
  );
}

/** The completed-work rollup from the work-item spine. */
function CompletedWorkStat({ count }: { readonly count: number }) {
  const t = useTranslations("student.reports.body");
  return (
    <div className="flex items-center gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[var(--color-success-light)] text-[var(--color-success)]">
        <ListChecks aria-hidden="true" className="size-5" />
      </span>
      <div className="min-w-0">
        <p className="text-[20px] font-semibold leading-none tabular-nums text-[var(--color-text)]">
          {count}
        </p>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("completedWork", { count })}
        </p>
      </div>
    </div>
  );
}

/** One weak concept: name + an honest mastery meter (never a grade). */
function WeakPointRow({ point }: { readonly point: ReportWeakPoint }) {
  const t = useTranslations("student.reports.body");
  const pct = Math.round(Math.min(Math.max(point.mastery_score, 0), 1) * 100);
  return (
    <li className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[14px] font-medium text-[var(--color-text)]">
          {point.name}
        </span>
        <span className="shrink-0 text-[12px] font-semibold tabular-nums text-[var(--color-text-secondary)]">
          {t("mastery", { pct })}
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={point.name}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-1.5 w-full overflow-hidden rounded-[var(--radius-pill)] bg-[var(--color-surface-hover)]"
      >
        <div
          className="h-full rounded-[var(--radius-pill)] bg-[var(--color-gold)]"
          style={{ width: `${pct}%` }}
        />
      </div>
    </li>
  );
}
